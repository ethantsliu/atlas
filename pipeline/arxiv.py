#!/usr/bin/env python3
"""Add arXiv abstracts and bibliographic metadata in restartable batches."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from identifiers import ARXIV_ID, OLD_ARXIV_ID, canonical_id
from files import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data/source/papers.json"
OUTPUT_PATH = ROOT / "data/generated/papers_enriched.json"
ENRICHMENT_STATUS_PATH = ROOT / "data/generated/arxiv_enrichment_status.json"
OVERRIDES_PATH = ROOT / "data/source/overrides.json"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
FETCHED_FIELDS = (
    "arxiv_id",
    "title",
    "abstract",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "comment",
)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split())


def paper_id(url: str) -> str | None:
    modern = ARXIV_ID.search(url)
    if modern:
        return modern.group(1).lower()
    old = OLD_ARXIV_ID.search(url)
    return old.group(1).lower() if old else None


def entry_identifier(raw_id: str) -> str:
    """Normalize modern and category-prefixed IDs returned by the Atom API."""
    return paper_id(raw_id) or re.sub(r"v\d+$", "", raw_id.rsplit("/", 1)[-1])


def merge_record(paper: dict, override: dict, prior: dict | None = None) -> dict:
    """Rebuild one row from current source plus cached API fields and overrides."""
    identifier = override.get("arxiv_id") or paper_id(paper.get("url", ""))
    record = {**paper, "reading_depth": "metadata"}
    if prior and identifier and prior.get("arxiv_id") == identifier:
        record.update({key: prior[key] for key in FETCHED_FIELDS if key in prior})
        if record.get("abstract"):
            record["reading_depth"] = "abstract"
    record.update(override)
    stable_id, identifier_kind = canonical_id(paper, override)
    record["stable_id"] = stable_id
    record["identifier_kind"] = identifier_kind
    return record


def fetch_batch(ids: list[str]) -> dict[str, dict]:
    query = urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)})
    request = urllib.request.Request(
        f"https://export.arxiv.org/api/query?{query}",
        headers={"User-Agent": "atlas/0.1 (local research tool)"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        root = ET.fromstring(response.read())
    result = {}
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = clean(entry.findtext(f"{ATOM}id")) or ""
        identifier = entry_identifier(raw_id)
        primary = entry.find(f"{ARXIV}primary_category")
        result[identifier] = {
            "arxiv_id": identifier,
            "title": clean(entry.findtext(f"{ATOM}title")),
            "abstract": clean(entry.findtext(f"{ATOM}summary")),
            "authors": [
                clean(author.findtext(f"{ATOM}name"))
                for author in entry.findall(f"{ATOM}author")
            ],
            "categories": [
                node.attrib.get("term") for node in entry.findall(f"{ATOM}category")
            ],
            "primary_category": primary.attrib.get("term")
            if primary is not None
            else None,
            "published": clean(entry.findtext(f"{ATOM}published")),
            "updated": clean(entry.findtext(f"{ATOM}updated")),
            "comment": clean(entry.findtext(f"{ARXIV}comment")),
        }
    return result


def write_enrichment_status(records: list[dict], failures: list[str]) -> None:
    """Write stage-local diagnostics without overwriting corpus coverage."""
    levels: dict[str, int] = {}
    for record in records:
        level = record.get("reading_depth", "metadata")
        levels[level] = levels.get(level, 0) + 1
    progress = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(records),
        "by_reading_depth": levels,
        "abstract_coverage": round(levels.get("abstract", 0) / max(1, len(records)), 4),
        "full_text_coverage": round(
            (levels.get("full_text", 0) + levels.get("verified", 0))
            / max(1, len(records)),
            4,
        ),
        "failed_arxiv_ids": failures,
    }
    atomic_write_text(ENRICHMENT_STATUS_PATH, json.dumps(progress, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=75)
    parser.add_argument("--delay", type=float, default=3.1)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    existing = {}
    if args.resume and OUTPUT_PATH.exists():
        existing = {
            record["id"]: record
            for record in json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        }
    records = []
    pending: dict[str, list[int]] = {}
    for paper in source:
        override = overrides.get(str(paper["id"]), {})
        record = merge_record(paper, override, existing.get(paper["id"]))
        records.append(record)
        identifier = override.get("arxiv_id") or paper_id(paper.get("url", ""))
        if identifier and not record.get("abstract"):
            pending.setdefault(identifier, []).append(len(records) - 1)

    ids = list(pending)
    failures: list[str] = []
    batch_count = (len(ids) + args.batch_size - 1) // args.batch_size
    if args.max_batches is not None:
        batch_count = min(batch_count, args.max_batches)
    for batch_index in range(batch_count):
        batch = ids[batch_index * args.batch_size : (batch_index + 1) * args.batch_size]
        try:
            metadata = fetch_batch(batch)
        except Exception as exc:  # Keep partial progress restartable.
            print(f"batch {batch_index + 1}/{batch_count} failed: {exc}")
            failures.extend(batch)
            continue
        for identifier in batch:
            item = metadata.get(identifier)
            if not item:
                failures.append(identifier)
                continue
            for index in pending[identifier]:
                paper = source[index]
                override = overrides.get(str(paper["id"]), {})
                records[index] = merge_record(paper, override, item)
        atomic_write_text(
            OUTPUT_PATH, json.dumps(records, ensure_ascii=False, indent=2) + "\n"
        )
        write_enrichment_status(records, failures)
        print(
            f"batch {batch_index + 1}/{batch_count}: enriched {len(metadata)} records"
        )
        if batch_index + 1 < batch_count:
            time.sleep(args.delay)

    atomic_write_text(
        OUTPUT_PATH, json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    )
    write_enrichment_status(records, failures)


if __name__ == "__main__":
    main()
