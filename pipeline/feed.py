#!/usr/bin/env python3
"""Fetch, audit, rank, and publish exhaustive daily arXiv intake."""

from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from files import atomic_write_bytes, atomic_write_text
from identifiers import ARXIV_ID, OLD_ARXIV_ID
from rank import load_rules, rank_day
from urls import open_public, read_limited

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "data/source/feed.json"
FEED_ROOT = ROOT / "data/generated/feed"
PUBLIC_ROOT = ROOT / "web/public/data/feed"
API_URL = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
OPEN = "{http://a9.com/-/spec/opensearch/1.1/}"
USER_AGENT = "atlas/0.2 (daily research discovery)"
PAGE_LIMIT = 12_000_000
RETRY_CODES = {429, 500, 502, 503, 504}
RETRY_LIMIT = 6


def clean(value: str | None) -> str:
    """Collapse feed whitespace without losing Unicode content."""
    return " ".join((value or "").split())


def paper_id(value: str) -> str:
    """Normalize modern or legacy arXiv identifiers and remove versions."""
    modern = ARXIV_ID.search(value)
    if modern:
        return modern.group(1).lower()
    legacy = OLD_ARXIV_ID.search(value)
    if legacy:
        return legacy.group(1).lower()
    return value.rsplit("/", 1)[-1].split("v", 1)[0].lower()


def parse_entry(entry: ET.Element) -> dict:
    """Convert one Atom entry into stable metadata used by ranking and UI."""
    raw_id = clean(entry.findtext(f"{ATOM}id"))
    primary = entry.find(f"{ARXIV}primary_category")
    identifier = paper_id(raw_id)
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": clean(entry.findtext(f"{ATOM}title")),
        "abstract": clean(entry.findtext(f"{ATOM}summary")),
        "authors": [
            clean(author.findtext(f"{ATOM}name"))
            for author in entry.findall(f"{ATOM}author")
        ],
        "categories": [
            node.attrib["term"]
            for node in entry.findall(f"{ATOM}category")
            if node.attrib.get("term")
        ],
        "primary_category": primary.attrib.get("term", "")
        if primary is not None
        else "",
        "published": clean(entry.findtext(f"{ATOM}published")),
        "updated": clean(entry.findtext(f"{ATOM}updated")),
        "comment": clean(entry.findtext(f"{ARXIV}comment")),
    }


def parse_page(body: bytes) -> tuple[int, list[dict]]:
    """Parse total count and entries from one bounded Atom response."""
    root = ET.fromstring(body)
    total_text = clean(root.findtext(f"{OPEN}totalResults"))
    if not total_text.isdigit():
        raise RuntimeError("arXiv response omitted a valid totalResults value")
    return int(total_text), [
        parse_entry(entry) for entry in root.findall(f"{ATOM}entry")
    ]


def day_query(day: date) -> str:
    """Build the GMT submitted-date query covering one complete calendar day."""
    stamp = day.strftime("%Y%m%d")
    return f"submittedDate:[{stamp}0000 TO {stamp}2359]"


def page_url(day: date, start: int, size: int) -> str:
    """Encode one chronological arXiv API page request."""
    query = urllib.parse.urlencode(
        {
            "search_query": day_query(day),
            "start": start,
            "max_results": size,
            "sortBy": "submittedDate",
            "sortOrder": "ascending",
        }
    )
    return f"{API_URL}?{query}"


def fetch_once(day: date, start: int, size: int) -> tuple[int, list[dict]]:
    """Make one safe, bounded arXiv page request."""
    request = urllib.request.Request(
        page_url(day, start, size), headers={"User-Agent": USER_AGENT}
    )
    with open_public(request, timeout=90) as response:
        return parse_page(read_limited(response, PAGE_LIMIT))


def retry_delay(error: Exception, attempt: int) -> float:
    """Respect Retry-After while bounding exponential transient backoff."""
    if isinstance(error, HTTPError) and error.headers:
        value = error.headers.get("Retry-After", "")
        if value.isdigit():
            return min(120.0, max(3.1, float(value)))
    return min(120.0, 3.1 * (2**attempt))


def fetch_page(day: date, start: int, size: int) -> tuple[int, list[dict]]:
    """Retry one arXiv page only for temporary service failures."""
    for attempt in range(RETRY_LIMIT):
        failure: Exception
        try:
            return fetch_once(day, start, size)
        except HTTPError as error:
            if error.code not in RETRY_CODES or attempt + 1 == RETRY_LIMIT:
                raise
            failure = error
        except (TimeoutError, URLError) as error:
            if attempt + 1 == RETRY_LIMIT:
                raise
            failure = error
        time.sleep(retry_delay(failure, attempt))
    raise RuntimeError("arXiv retry loop ended unexpectedly")


def fetch_day(day: date, size: int = 500, delay: float = 3.1) -> dict:
    """Fetch every result for one day and reject incomplete pagination."""
    papers: list[dict] = []
    total: int | None = None
    page_count = 0
    while total is None or len(papers) < total:
        page_total, page = fetch_page(day, len(papers), size)
        if total is None:
            total = page_total
        elif page_total != total:
            raise RuntimeError("arXiv totalResults changed during pagination")
        if not page and len(papers) < total:
            raise RuntimeError("arXiv pagination ended before every result was fetched")
        papers.extend(page)
        page_count += 1
        if len(papers) < total:
            time.sleep(delay)
    if len(papers) != total:
        raise RuntimeError(f"arXiv returned {len(papers)} entries for total {total}")
    return {
        "source_total": total,
        "fetched_count": len(papers),
        "unique_count": len({paper["id"] for paper in papers}),
        "page_count": page_count,
        "query": day_query(day),
        "papers": papers,
    }


def make_day(day: date, intake: dict, rules: dict, shortlist: int) -> dict:
    """Create a public day payload while retaining every relevant result."""
    ranked = rank_day(intake["papers"], rules)
    shortlist_ids = [paper["id"] for paper in ranked[:shortlist]]
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "policy_version": rules["version"],
        "date": day.isoformat(),
        "generated_at": now,
        "source": {
            "provider": "arXiv",
            "query": intake["query"],
            "timezone": "UTC",
            "complete": intake["fetched_count"] == intake["source_total"],
            "source_total": intake["source_total"],
            "fetched_count": intake["fetched_count"],
            "unique_count": intake["unique_count"],
            "page_count": intake["page_count"],
        },
        "relevant_count": len(ranked),
        "shortlist_count": len(shortlist_ids),
        "shortlist_ids": shortlist_ids,
        "papers": ranked,
    }


def raw_payload(day: date, intake: dict) -> bytes:
    """Compress the complete source intake for audit and offline re-scoring."""
    payload = {
        "schema_version": 1,
        "date": day.isoformat(),
        **intake,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return gzip.compress(body, compresslevel=9, mtime=0)


def day_summary(payload: dict) -> dict:
    """Project one public day into the lightweight discovery index."""
    return {
        "date": payload["date"],
        "generated_at": payload["generated_at"],
        "source_total": payload["source"]["source_total"],
        "fetched_count": payload["source"]["fetched_count"],
        "relevant_count": payload["relevant_count"],
        "shortlist_count": payload["shortlist_count"],
        "complete": payload["source"]["complete"],
        "path": f"/data/feed/{payload['date']}.json",
    }


def build_index(root: Path) -> dict:
    """Rebuild the date index from complete published day artifacts."""
    days = []
    for path in root.glob("????-??-??.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        days.append(day_summary(payload))
    days.sort(key=lambda item: item["date"], reverse=True)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
    }


def save_day(day: date, intake: dict, payload: dict) -> None:
    """Atomically publish raw, private, and web-facing daily artifacts."""
    name = f"{day.isoformat()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_bytes(FEED_ROOT / "raw" / f"{name}.gz", raw_payload(day, intake))
    atomic_write_text(FEED_ROOT / name, text)
    atomic_write_text(PUBLIC_ROOT / name, text)
    index = build_index(FEED_ROOT)
    index_text = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(FEED_ROOT / "index.json", index_text)
    atomic_write_text(PUBLIC_ROOT / "index.json", index_text)


def day_range(end: date, count: int) -> list[date]:
    """Return an inclusive catch-up window in chronological order."""
    start = end - timedelta(days=count - 1)
    return [start + timedelta(days=offset) for offset in range(count)]


def parse_args() -> argparse.Namespace:
    """Parse a small CLI suitable for local and scheduled catch-up runs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--delay", type=float, default=3.1)
    parser.add_argument("--shortlist", type=int)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Reject unsafe paging, timing, and window parameters."""
    if args.days < 1:
        raise SystemExit("--days must be at least 1")
    if not 1 <= args.page_size <= 2000:
        raise SystemExit("--page-size must be between 1 and 2000")
    if args.delay < 3.0:
        raise SystemExit("--delay must be at least 3 seconds")
    if args.shortlist is not None and args.shortlist < 1:
        raise SystemExit("--shortlist must be at least 1")


def main() -> None:
    """Fetch and publish a complete recent daily window."""
    args = parse_args()
    validate_args(args)
    rules = load_rules(RULES_PATH)
    end = args.date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    shortlist = args.shortlist or int(rules["shortlist_size"])
    days = day_range(end, args.days)
    for index, day in enumerate(days):
        print(f"fetching {day.isoformat()} from arXiv")
        intake = fetch_day(day, size=args.page_size, delay=args.delay)
        payload = make_day(day, intake, rules, shortlist)
        save_day(day, intake, payload)
        print(
            f"published {payload['relevant_count']} relevant papers "
            f"from {intake['source_total']} submissions"
        )
        if index + 1 < len(days):
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
