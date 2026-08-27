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
from titles import valid_title
from urls import is_public_url, open_public, read_limited

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://metacircleai.github.io/ziming-paper-collection/data/papers.json"
SOURCE_PATH = ROOT / "data/source/papers.json"
MANIFEST_PATH = ROOT / "data/generated/corpus_manifest.json"
OVERRIDES_PATH = ROOT / "data/source/overrides.json"
TITLES_PATH = ROOT / "data/source/titles.json"
COLLECTION_FIELDS = {"id", "title", "url", "section", "tags", "note", "source"}
PUBLIC_FIELDS = ("id", "title", "url", "source")
MAX_COLLECTION_BYTES = 16 * 1024 * 1024
EXCLUDED_CONTEXT_IDS = frozenset({2092, 2110, 2111, 2112, 2125, 2170})
EXCLUDED_ALIAS_IDS = frozenset(
    {
        882,
        898,
        1459,
        1471,
        1534,
        1573,
        1685,
        1720,
        2094,
        2095,
        2129,
        2134,
        2137,
        2147,
        2158,
        2168,
        2169,
    }
)


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


def public_collection(
    papers: list[dict], titles: dict[str, str] | None = None
) -> list[dict]:
    """Project research rows onto general public source fields only."""
    canonical = titles or {}
    result = []
    for paper in papers:
        if paper["id"] in EXCLUDED_CONTEXT_IDS | EXCLUDED_ALIAS_IDS:
            continue
        row = {key: paper[key] for key in PUBLIC_FIELDS}
        row["title"] = canonical.get(str(paper["id"]), row["title"])
        if valid_title(row["title"], strict=True):
            result.append(row)
    return result


def main() -> None:
    request = Request(SOURCE_URL, headers={"User-Agent": "atlas/0.1"})
    with open_public(request, timeout=60) as response:
        raw = read_limited(response, MAX_COLLECTION_BYTES)
    upstream = validate_collection(json.loads(raw))
    titles = json.loads(TITLES_PATH.read_text(encoding="utf-8"))
    papers = public_collection(upstream, titles)
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    ids = [paper.get("id") for paper in papers]
    excluded_context = sum(paper["id"] in EXCLUDED_CONTEXT_IDS for paper in upstream)
    excluded_aliases = sum(paper["id"] in EXCLUDED_ALIAS_IDS for paper in upstream)

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
        "excluded_private_context": excluded_context,
        "excluded_duplicate_papers": excluded_aliases,
        "excluded_unsafe_title": (
            len(upstream) - len(papers) - excluded_context - excluded_aliases
        ),
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
