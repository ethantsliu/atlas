#!/usr/bin/env python3
"""Promote validated daily arXiv papers into the canonical Atlas corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path

from feedcheck import DAY_NAME, validate_day
from files import atomic_write_text
from scrub import scrub_paper


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data/source/papers.json"
ENRICHED_PATH = ROOT / "data/generated/papers_enriched.json"
FEED_ROOT = ROOT / "data/generated/feed"
REPORT_PATH = ROOT / "data/generated/promotion.json"
ARXIV_ID = re.compile(r"^(\d{4})\.(\d{4,5})$")
ID_OFFSET = 1_000_000_000


def corpus_id(identifier: str) -> int:
    """Map a modern arXiv ID to a stable, collision-resistant numeric row ID."""
    match = ARXIV_ID.fullmatch(identifier)
    if match is None:
        raise ValueError(f"Unsupported daily arXiv ID: {identifier}")
    month, number = match.groups()
    return ID_OFFSET + int(month) * 100_000 + int(number)


def feed_record(paper: dict) -> dict:
    """Convert one validated feed paper into the enriched corpus contract."""
    identifier = paper["id"]
    record = {
        "id": corpus_id(identifier),
        "title": paper["title"],
        "url": paper["url"],
        "source": "arXiv",
        "reading_depth": "abstract",
        "arxiv_id": identifier,
        "abstract": paper["abstract"],
        "authors": list(paper["authors"]),
        "categories": list(paper["categories"]),
        "primary_category": paper.get("primary_category", ""),
        "published": paper.get("published", ""),
        "updated": paper.get("updated", ""),
        "comment": paper.get("comment", ""),
        "stable_id": f"arxiv:{identifier}",
        "identifier_kind": "arxiv",
        "relevance": paper["relevance"],
        "interest": paper["interest"],
    }
    return scrub_paper(record)


def base_records(source: list[dict], enriched: list[dict]) -> list[dict]:
    """Recover the fixed collection rows from a previously promoted corpus."""
    by_id = {record.get("id"): record for record in enriched}
    source_ids = [paper["id"] for paper in source]
    missing = [identifier for identifier in source_ids if identifier not in by_id]
    if missing:
        raise RuntimeError(
            f"Enriched corpus is missing {len(missing)} base collection rows"
        )
    return [scrub_paper(by_id[identifier]) for identifier in source_ids]


def build_corpus(base: list[dict], days: list[dict]) -> tuple[list[dict], dict]:
    """Merge every relevance-positive daily row after canonical deduplication."""
    base_ids = {record.get("stable_id") for record in base}
    promoted: dict[str, dict] = {}
    base_duplicates = 0
    repeat_rows = 0
    input_rows = 0
    for payload in sorted(days, key=lambda item: item["date"]):
        for paper in payload["papers"]:
            input_rows += 1
            stable_id = f"arxiv:{paper['id']}"
            if stable_id in base_ids:
                base_duplicates += 1
                continue
            if stable_id in promoted:
                repeat_rows += 1
                if paper.get("updated", "") <= promoted[stable_id].get("updated", ""):
                    continue
            promoted[stable_id] = feed_record(paper)

    additions = sorted(promoted.values(), key=lambda record: record["arxiv_id"])
    row_ids = [record["id"] for record in [*base, *additions]]
    if len(row_ids) != len(set(row_ids)):
        raise RuntimeError("Promoted corpus contains a numeric ID collision")

    dates = sorted(payload["date"] for payload in days)
    report = {
        "schema_version": 1,
        "days": dates,
        "base_count": len(base),
        "input_rows": input_rows,
        "base_duplicates": base_duplicates,
        "repeat_rows": repeat_rows,
        "promoted_count": len(additions),
        "corpus_count": len(base) + len(additions),
        "newest_day": dates[-1] if dates else None,
        "status": "valid",
    }
    return [*base, *additions], report


def load_days(root: Path = FEED_ROOT) -> list[dict]:
    """Load only complete feed days whose raw lineage also validates."""
    paths = sorted(
        path for path in root.glob("*.json") if DAY_NAME.fullmatch(path.name)
    )
    return [validate_day(path) for path in paths]


def promote() -> tuple[list[dict], dict]:
    """Build and atomically publish the promoted corpus and its audit report."""
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    enriched = json.loads(ENRICHED_PATH.read_text(encoding="utf-8"))
    corpus, report = build_corpus(base_records(source, enriched), load_days())
    atomic_write_text(
        ENRICHED_PATH,
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
    )
    atomic_write_text(REPORT_PATH, json.dumps(report, indent=2) + "\n")
    return corpus, report


def main() -> None:
    corpus, report = promote()
    print(
        f"Promoted {report['promoted_count']:,} daily papers; "
        f"corpus now has {len(corpus):,} entries"
    )


if __name__ == "__main__":
    main()
