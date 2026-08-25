#!/usr/bin/env python3
"""Refresh idea-level competitor provenance from primary metadata records.

arXiv records are resolved in batches through the official Atom API. Other
archives remain explicitly unresolved unless a separately inspected record is
already present in the sidecar; the updater never invents a publication date or
maps a venue year to an arbitrary day.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from pathlib import Path

from competitors import (
    LEGACY_UNVERSIONED,
    PROVENANCE_SCHEMA_VERSION,
    VERSION_VERIFIED,
    load_competitors,
    titles_match,
    validate_provenance_payload,
)
from files import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
IDEAS_PATH = ROOT / "data/source/flagships.json"
OUTPUT_PATH = ROOT / "data/source/competitors.json"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
USER_AGENT = "atlas/1.0 (competitor provenance audit)"


def collect_sources(ideas: list[dict]) -> dict[str, dict]:
    """Index duplicate brief rows and reject inconsistent primary URLs."""
    sources: dict[str, dict] = {}
    titles: dict[str, set[str]] = defaultdict(set)
    urls: dict[str, set[str]] = defaultdict(set)
    for idea in ideas:
        for competitor in idea.get("brief", {}).get("competitive_landscape", []):
            canonical_id = competitor["canonical_id"]
            titles[canonical_id].add(competitor["title"])
            urls[canonical_id].add(competitor["url"])
            sources[canonical_id] = {
                "url": competitor["url"],
                "title": competitor["title"],
            }
    for canonical_id, variants in urls.items():
        identifier = arxiv_id(canonical_id)
        if len(variants) > 1 and (
            identifier is None
            or any(
                re.fullmatch(
                    rf"/abs/{re.escape(identifier)}(?:v\d+)?",
                    urllib.parse.urlparse(url).path,
                )
                is None
                for url in variants
            )
        ):
            raise RuntimeError(
                f"Competitor {canonical_id} has inconsistent primary URLs: "
                f"{sorted(variants)}"
            )
    for canonical_id, variants in titles.items():
        if any(
            not titles_match(next(iter(variants)), candidate) for candidate in variants
        ):
            raise RuntimeError(
                f"Competitor {canonical_id} has inconsistent title variants: "
                f"{sorted(variants)}"
            )
    return sources


def arxiv_id(canonical_id: str) -> str | None:
    return (
        canonical_id.removeprefix("arxiv:")
        if canonical_id.startswith("arxiv:")
        else None
    )


def source_kind(canonical_id: str) -> str:
    prefix = canonical_id.partition(":")[0]
    if prefix == "arxiv":
        return "arxiv"
    if prefix == "openreview":
        return "openreview"
    if prefix in {"acl", "neurips", "pmlr"}:
        return "official-proceedings"
    return "publisher"


def fetch_arxiv_batch(identifiers: list[str], timeout: float) -> dict[str, dict]:
    """Return the current exact revision metadata for one API batch."""
    query = urllib.parse.urlencode(
        {"id_list": ",".join(identifiers), "max_results": len(identifiers)}
    )
    request = urllib.request.Request(
        f"{ARXIV_API}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        root = ET.fromstring(response.read())

    records: dict[str, dict] = {}
    for entry in root.findall("atom:entry", ARXIV_NAMESPACE):
        identifier = (entry.findtext("atom:id", "", ARXIV_NAMESPACE)).rsplit("/", 1)[-1]
        match = re.fullmatch(r"(.+)(v\d+)", identifier)
        if not match:
            continue
        base_id, version = match.groups()
        records[base_id] = {
            "version": version,
            "date": entry.findtext("atom:updated", "", ARXIV_NAMESPACE)[:10],
            "title": " ".join(
                entry.findtext("atom:title", "", ARXIV_NAMESPACE).split()
            ),
        }
    return records


def fetch_arxiv_records(
    identifiers: list[str], *, batch_size: int, timeout: float, pause: float
) -> dict[str, dict]:
    """Fetch sorted batches with an arXiv-friendly pause between requests."""
    fetched: dict[str, dict] = {}
    for start in range(0, len(identifiers), batch_size):
        if start:
            time.sleep(pause)
        batch = identifiers[start : start + batch_size]
        fetched.update(fetch_arxiv_batch(batch, timeout))
    return fetched


def legacy_record(
    canonical_id: str, source: dict, checked_at: str, reason: str
) -> dict:
    return {
        "provenance_status": LEGACY_UNVERSIONED,
        "source_kind": source_kind(canonical_id),
        "checked_at": checked_at,
        "source_locator": source["url"],
        "verified_title": source["title"],
        "unresolved_reason": reason,
    }


def build_payload(
    sources: dict[str, dict],
    fetched_arxiv: dict[str, dict],
    existing: dict[str, dict],
    checked_at: str,
) -> dict:
    """Combine fresh primary metadata with retained manual primary audits."""
    records: dict[str, dict] = {}
    for canonical_id in sorted(sources):
        source = sources[canonical_id]
        identifier = arxiv_id(canonical_id)
        if identifier is None:
            retained = existing.get(canonical_id)
            if retained and retained.get("provenance_status") == VERSION_VERIFIED:
                records[canonical_id] = retained
            else:
                records[canonical_id] = legacy_record(
                    canonical_id,
                    source,
                    checked_at,
                    "Exact revision and full ISO source date require a manual primary-record audit.",
                )
            continue

        metadata = fetched_arxiv.get(identifier)
        if metadata is None:
            records[canonical_id] = legacy_record(
                canonical_id,
                source,
                checked_at,
                "The official arXiv API returned no matching record.",
            )
            continue
        if not titles_match(source["title"], metadata["title"]):
            records[canonical_id] = legacy_record(
                canonical_id,
                source,
                checked_at,
                f"Primary title mismatch: {metadata['title']}",
            )
            continue
        version = metadata["version"]
        records[canonical_id] = {
            "provenance_status": VERSION_VERIFIED,
            "source_kind": "arxiv",
            "source_version": f"arXiv:{identifier}{version}",
            "source_date": metadata["date"],
            "checked_at": checked_at,
            "source_locator": f"https://arxiv.org/abs/{identifier}{version}",
            "verified_title": metadata["title"],
        }
    payload = {"schema_version": PROVENANCE_SCHEMA_VERSION, "records": records}
    validate_provenance_payload(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checked-at", default=date.today().isoformat())
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--pause", type=float, default=3.0)
    parser.add_argument("--ideas", type=Path, default=IDEAS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    date.fromisoformat(args.checked_at)
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")

    ideas = json.loads(args.ideas.read_text(encoding="utf-8"))
    sources = collect_sources(ideas)
    identifiers = sorted(
        identifier
        for canonical_id in sources
        if (identifier := arxiv_id(canonical_id)) is not None
    )
    existing = load_competitors(args.output) if args.output.is_file() else {}
    fetched = fetch_arxiv_records(
        identifiers,
        batch_size=args.batch_size,
        timeout=args.timeout,
        pause=args.pause,
    )
    payload = build_payload(sources, fetched, existing, args.checked_at)
    atomic_write_text(
        args.output,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    verified = sum(
        row["provenance_status"] == VERSION_VERIFIED
        for row in payload["records"].values()
    )
    print(
        f"Wrote {len(payload['records'])} records: {verified} version-verified, "
        f"{len(payload['records']) - verified} legacy-unversioned"
    )


if __name__ == "__main__":
    main()
