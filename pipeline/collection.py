#!/usr/bin/env python3
"""Fetch and validate the public collection manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request

from identifiers import canonical_id
from files import atomic_write_bytes, atomic_write_text
from urls import is_public_url, open_public, read_limited

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://metacircleai.github.io/ziming-paper-collection/data/papers.json"
SOURCE_PATH = ROOT / "data/source/papers.json"
MANIFEST_PATH = ROOT / "data/generated/corpus_manifest.json"
OVERRIDES_PATH = ROOT / "data/source/overrides.json"
COLLECTION_FIELDS = {"id", "title", "url", "section", "tags", "note", "source"}
MAX_COLLECTION_BYTES = 16 * 1024 * 1024
PRIVATE_CONTEXT_IDS = frozenset({2092, 2111, 2112})


def validate_row(paper: object, index: int) -> dict:
    """Validate one externally supplied collection record before persistence."""
    if not isinstance(paper, dict) or set(paper) != COLLECTION_FIELDS:
        raise RuntimeError(f"Collection row {index} has an invalid field set")
    if (
        not isinstance(paper["id"], int)
        or isinstance(paper["id"], bool)
        or paper["id"] <= 0
    ):
        raise RuntimeError(f"Collection row {index} has an invalid ID")
    for field in ("title", "section", "source"):
        if not isinstance(paper[field], str) or not paper[field].strip():
            raise RuntimeError(f"Collection row {index} has invalid {field}")
    if not is_public_url(paper["url"]):
        raise RuntimeError(f"Collection row {index} has an unsafe URL")
    tags = paper["tags"]
    if (
        not isinstance(tags, list)
        or not all(isinstance(tag, str) and tag.strip() for tag in tags)
        or not (paper["note"] is None or isinstance(paper["note"], str))
    ):
        raise RuntimeError(f"Collection row {index} has invalid tags or note")
    return paper


def validate_collection(papers: object) -> list[dict]:
    """Validate the complete remote collection and its unique row IDs."""
    if not isinstance(papers, list) or len(papers) < 2000:
        count = len(papers) if isinstance(papers, list) else "invalid JSON"
        raise RuntimeError(f"Expected at least 2,000 papers; received {count}")
    rows = [validate_row(paper, index) for index, paper in enumerate(papers)]
    ids = [paper["id"] for paper in rows]
    if len(set(ids)) != len(ids):
        raise RuntimeError("Collection contains duplicate paper IDs")
    return rows


def public_collection(papers: list[dict]) -> list[dict]:
    """Omit account-linked context while preserving every research paper row."""
    return [paper for paper in papers if paper["id"] not in PRIVATE_CONTEXT_IDS]


def main() -> None:
    request = Request(SOURCE_URL, headers={"User-Agent": "atlas/0.1"})
    with open_public(request, timeout=60) as response:
        raw = read_limited(response, MAX_COLLECTION_BYTES)
    upstream = validate_collection(json.loads(raw))
    papers = public_collection(upstream)
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    ids = [paper.get("id") for paper in papers]

    source_bytes = (
        json.dumps(papers, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    atomic_write_bytes(SOURCE_PATH, source_bytes)

    by_source: dict[str, int] = {}
    canonical_ids = []
    for paper in papers:
        source = paper.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        canonical_ids.append(canonical_id(paper, overrides.get(str(paper["id"])))[0])
    manifest = {
        "source_url": SOURCE_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "upstream_sha256": hashlib.sha256(raw).hexdigest(),
        "upstream_entry_count": len(upstream),
        "excluded_private_context": len(upstream) - len(papers),
        "paper_count": len(papers),
        "unique_canonical_records": len(set(canonical_ids)),
        "duplicate_collection_entries": len(papers) - len(set(canonical_ids)),
        "unique_urls": len({paper.get("url") for paper in papers}),
        "unique_titles": len({paper.get("title") for paper in papers}),
        "by_source": dict(sorted(by_source.items())),
        "id_min": min(ids),
        "id_max": max(ids),
    }
    atomic_write_text(MANIFEST_PATH, json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
