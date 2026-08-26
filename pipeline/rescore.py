#!/usr/bin/env python3
"""Reapply the current ML scope policy to complete archived feed days."""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

from feed import (
    FEED_ROOT,
    PUBLIC_ROOT,
    RULES_PATH,
    build_index,
    make_day,
)
from files import atomic_write_text
from rank import load_rules


def load_raw(path: Path) -> tuple[date, dict]:
    """Load one complete raw day as the immutable rescoring input."""
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
        day = date.fromisoformat(payload.pop("date"))
    except (OSError, EOFError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Raw feed day is invalid: {path.name}") from error
    payload.pop("schema_version", None)
    if (
        payload.get("source_total") != payload.get("fetched_count")
        or payload.get("unique_count") != payload.get("source_total")
        or len(payload.get("papers", [])) != payload.get("source_total")
    ):
        raise ValueError(f"Raw feed day is incomplete: {path.name}")
    return day, payload


def rescore_day(
    day_path: Path,
    raw_path: Path,
    public_root: Path,
    rules: dict,
) -> dict:
    """Regenerate one public day without refetching or changing provenance time."""
    existing = json.loads(day_path.read_text(encoding="utf-8"))
    day, intake = load_raw(raw_path)
    if day_path.stem != day.isoformat():
        raise ValueError(f"Feed day path does not match raw date: {day_path.name}")
    payload = make_day(day, intake, rules, int(rules["shortlist_size"]))
    payload["generated_at"] = existing["generated_at"]
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(day_path, text)
    atomic_write_text(public_root / day_path.name, text)
    return payload


def rescore_all(
    feed_root: Path = FEED_ROOT,
    public_root: Path = PUBLIC_ROOT,
    rules_path: Path = RULES_PATH,
) -> dict:
    """Rescore every auditable feed day and rebuild its public index."""
    rules = load_rules(rules_path)
    paths = sorted(feed_root.glob("????-??-??.json"))
    for path in paths:
        rescore_day(
            path,
            feed_root / "raw" / f"{path.name}.gz",
            public_root,
            rules,
        )
    index = build_index(feed_root)
    text = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(feed_root / "index.json", text)
    atomic_write_text(public_root / "index.json", text)
    return index


def main() -> None:
    """Refresh all retained days under the current auditable policy."""
    index = rescore_all()
    print(f"Rescored {len(index['days']):,} complete arXiv days")


if __name__ == "__main__":
    main()
