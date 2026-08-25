#!/usr/bin/env python3
"""Pin structured readings to the exact extracted paper revision they review."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from ledger import load_json_lines
from paths import REVIEWED_READINGS_DIR
from files import atomic_write_text
from identity import SHA256, source_format, source_hash, valid_source

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data/generated/fulltext_index.jsonl"
READINGS_DIR = REVIEWED_READINGS_DIR


def source_locator(entry: dict) -> str:
    """Return the most specific stable source locator available in the index."""
    if entry.get("source_url"):
        return entry["source_url"]
    if entry.get("pdf_url"):
        return entry["pdf_url"]
    if entry.get("arxiv_id"):
        return f"https://arxiv.org/pdf/{entry['arxiv_id']}"
    return entry["stable_id"]


def provenance_for(entry: dict, reading_depth: str) -> dict:
    """Build the source pin expected for one reading depth."""
    timestamp = entry.get("processed_at")
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Source entry has an invalid extraction timestamp") from error
    page_count = entry.get("page_count")
    if (
        not valid_source(entry)
        or not SHA256.fullmatch(entry.get("text_sha256", ""))
        or not isinstance(page_count, int)
        or isinstance(page_count, bool)
        or page_count < 1
        or parsed.tzinfo is None
    ):
        raise ValueError("Source entry is not valid for reading provenance")
    review_pass = (
        "secondary-verified-v1"
        if reading_depth == "verified"
        else "primary-full-text-v1"
    )
    provenance = {
        "source_locator": source_locator(entry),
        "text_sha256": entry["text_sha256"],
        "page_count": entry["page_count"],
        "extracted_at": entry["processed_at"],
        "review_pass": review_pass,
    }
    if source_format(entry) == "pdf":
        provenance = {
            "source_locator": provenance.pop("source_locator"),
            "pdf_sha256": source_hash(entry),
            **provenance,
        }
    else:
        provenance = {
            "source_locator": provenance.pop("source_locator"),
            "source_format": source_format(entry),
            "source_sha256": source_hash(entry),
            **provenance,
        }
    return provenance


def with_source_pin(reading: dict, entry: dict) -> dict:
    """Insert the pin beside reading depth while retaining readable key order."""
    pinned = {}
    for key, value in reading.items():
        if key == "source_provenance":
            continue
        pinned[key] = value
        if key == "reading_depth":
            pinned["source_provenance"] = provenance_for(entry, value)
    return pinned


def pin_readings(readings_dir: Path, index_path: Path) -> tuple[int, int]:
    """Pin every reading with a successful indexed extraction."""
    entries = {
        entry["stable_id"]: entry
        for entry in load_json_lines(index_path)
        if entry.get("status") == "full_text_ok"
    }
    plans = []
    for path in sorted(readings_dir.glob("*.json")):
        reading = json.loads(path.read_text(encoding="utf-8"))
        stable_id = reading["stable_id"]
        if stable_id not in entries:
            raise RuntimeError(f"Reading has no successful extraction: {stable_id}")
        pinned = with_source_pin(reading, entries[stable_id])
        plans.append((path, reading, pinned))

    updated = 0
    unchanged = 0
    for path, reading, pinned in plans:
        if pinned == reading:
            unchanged += 1
            continue
        atomic_write_text(
            path,
            json.dumps(pinned, ensure_ascii=False, indent=2) + "\n",
        )
        updated += 1
    return updated, unchanged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--accept-current-source",
        action="store_true",
        help="Confirm that the indexed source revisions were reviewed before pinning",
    )
    args = parser.parse_args()
    if not args.accept_current_source:
        raise SystemExit(
            "Refusing to re-pin readings without --accept-current-source; "
            "inspect changed source revisions first."
        )
    updated, unchanged = pin_readings(READINGS_DIR, INDEX_PATH)
    print(f"Pinned {updated} readings; {unchanged} already matched the current source")


if __name__ == "__main__":
    main()
