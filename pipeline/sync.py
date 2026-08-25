#!/usr/bin/env python3
"""Synchronize public daily metadata into the hosted search database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from db import check_day, sync_corpus, sync_days

ROOT = Path(__file__).resolve().parents[1]
FEED_ROOT = ROOT / "data/generated/feed"
ATLAS_PATH = ROOT / "data/generated/atlas.json"
ENRICHED_PATH = ROOT / "data/generated/papers_enriched.json"
DAY_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
URL_ENV = "ATLAS_DATABASE_URL"


def parse_args() -> argparse.Namespace:
    """Parse safe hosted-sync options without accepting secrets on argv."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--feed-root", type=Path, default=FEED_ROOT)
    parser.add_argument("--keep-days", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--feed-only", action="store_true")
    mode.add_argument("--corpus-only", action="store_true")
    return parser.parse_args()


def load_days(root: Path, selected: str | None = None) -> list[dict]:
    """Load complete generated day payloads in chronological order."""
    if selected and not DAY_NAME.fullmatch(f"{selected}.json"):
        raise ValueError("Hosted sync date must use YYYY-MM-DD")
    paths = [root / f"{selected}.json"] if selected else list(root.glob("*.json"))
    paths = sorted(path for path in paths if DAY_NAME.fullmatch(path.name))
    payloads = []
    for path in paths:
        if not path.is_file():
            raise ValueError(f"Hosted sync day does not exist: {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        check_day(payload)
        if path.stem != payload.get("date"):
            raise ValueError(f"Hosted sync filename/date mismatch: {path.name}")
        payloads.append(payload)
    return payloads


def trim_days(payloads: list[dict], keep_days: int) -> list[dict]:
    """Limit routine uploads to the configured hosted retention window."""
    if keep_days < 1 or not payloads:
        return payloads
    newest = max(date.fromisoformat(payload["date"]) for payload in payloads)
    cutoff = newest - timedelta(days=keep_days - 1)
    return [
        payload for payload in payloads if date.fromisoformat(payload["date"]) >= cutoff
    ]


def load_corpus() -> tuple[dict, list[dict], str]:
    """Load the generated public corpus and matching enriched bibliography."""
    atlas_bytes = ATLAS_PATH.read_bytes()
    enriched_bytes = ENRICHED_PATH.read_bytes()
    atlas = json.loads(atlas_bytes)
    enriched = json.loads(enriched_bytes)
    if not isinstance(atlas, dict) or not isinstance(enriched, list):
        raise ValueError("Hosted corpus artifacts have invalid roots")
    digest = hashlib.sha256(atlas_bytes + b"\0" + enriched_bytes).hexdigest()
    return atlas, enriched, digest


def main() -> None:
    """Run a transactional sync or report the rows a dry run would write."""
    args = parse_args()
    if args.keep_days < 1:
        raise SystemExit("--keep-days must be at least 1")
    if args.corpus_only and args.date:
        raise SystemExit("--date cannot be combined with --corpus-only")
    payloads = [] if args.corpus_only else load_days(args.feed_root, args.date)
    if payloads and not args.date:
        payloads = trim_days(payloads, args.keep_days)
    paper_count = sum(len(payload["papers"]) for payload in payloads)
    atlas, enriched, digest = ({}, [], "") if args.feed_only else load_corpus()
    corpus_count = len(atlas.get("papers", []))
    if args.dry_run:
        print(
            json.dumps(
                {
                    "days": len(payloads),
                    "daily_papers": paper_count,
                    "corpus_papers": corpus_count,
                }
            )
        )
        return
    database_url = os.environ.get(URL_ENV, "")
    if not database_url:
        raise SystemExit(f"{URL_ENV} is required unless --dry-run is used")
    import psycopg

    with psycopg.connect(database_url) as connection:
        corpus_synced = sync_corpus(connection, atlas, enriched, digest) if atlas else 0
        daily_synced, cutoff = (
            sync_days(connection, payloads, args.keep_days) if payloads else (0, None)
        )
    print(
        json.dumps(
            {
                "days": len(payloads),
                "daily_papers": daily_synced,
                "corpus_papers": corpus_synced,
                "cutoff": str(cutoff) if cutoff else None,
            }
        )
    )


if __name__ == "__main__":
    main()
