#!/usr/bin/env python3
"""Resumably harvest exhaustive arXiv metadata into monthly archive shards."""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

from archive import ARCHIVE_ROOT, MANIFEST_NAME, add_day, read_manifest
from feed import RETRY_CODES, RULES_PATH, fetch_day
from rank import load_rules


def date_range(start: date, end: date) -> list[date]:
    """Return an inclusive historical date range."""
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def completed_days(root: Path) -> set[str]:
    """Read completed source days without downloading every month shard."""
    manifest = read_manifest(root)
    return {
        value
        for shard in manifest["shards"]
        for value in shard.get("dates", [])
        if isinstance(value, str)
    }


def pending_days(
    start: date,
    end: date,
    completed: set[str],
    limit: int,
) -> list[date]:
    """Keep yesterday current, then fill the earliest historical gaps."""
    if start > end:
        raise ValueError("Backfill start must not follow its end")
    if limit < 1:
        raise ValueError("Backfill limit must be positive")
    missing = [
        day for day in date_range(start, end) if day.isoformat() not in completed
    ]
    if not missing:
        return []
    ordered = [missing[-1], *missing[:-1]]
    return ordered[:limit]


def parse_args() -> argparse.Namespace:
    """Parse bounded historical harvesting options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2020, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--max-days", type=int, default=31)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--delay", type=float, default=3.1)
    parser.add_argument("--root", type=Path, default=ARCHIVE_ROOT)
    parser.add_argument("--plan", type=Path)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Reject unbounded or arXiv-hostile backfill settings."""
    if args.max_days < 1:
        raise SystemExit("--max-days must be at least 1")
    if not 1 <= args.page_size <= 2000:
        raise SystemExit("--page-size must be between 1 and 2000")
    if args.delay < 3.0:
        raise SystemExit("--delay must be at least 3 seconds")


def harvest_days(
    days: list[date],
    root: Path,
    rules: dict,
    size: int,
    delay: float,
    fetcher=fetch_day,
) -> tuple[int, str | None]:
    """Checkpoint complete dates and defer only exhausted transient failures."""
    completed = 0
    for index, day in enumerate(days):
        print(f"archiving {day.isoformat()} from arXiv", flush=True)
        try:
            intake = fetcher(day, size=size, delay=delay)
        except HTTPError as error:
            if error.code not in RETRY_CODES:
                raise
            return completed, f"HTTP {error.code}"
        except (TimeoutError, URLError) as error:
            return completed, type(error).__name__
        manifest = add_day(root, day, intake, rules)
        completed += 1
        print(
            f"archived {manifest['counts']['all']:,} total metadata records",
            flush=True,
        )
        if index + 1 < len(days):
            time.sleep(delay)
    return completed, None


def main() -> None:
    """Harvest the next bounded slice and checkpoint every complete day."""
    args = parse_args()
    validate_args(args)
    end = args.end or (datetime.now(timezone.utc).date() - timedelta(days=1))
    days = pending_days(args.start, end, completed_days(args.root), args.max_days)
    if args.plan:
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(
            json.dumps(
                {
                    "days": [day.isoformat() for day in days],
                    "months": sorted({day.strftime("%Y-%m") for day in days}),
                    "manifest": str(args.root / MANIFEST_NAME),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"planned {len(days):,} missing archive days")
        return
    rules = load_rules(RULES_PATH)
    if not days:
        print("Historical arXiv archive is current")
        return
    completed, deferred = harvest_days(
        days,
        args.root,
        rules,
        args.page_size,
        args.delay,
    )
    if deferred:
        print(
            f"checkpointed {completed:,} dates; deferred the next date after {deferred}",
            flush=True,
        )


if __name__ == "__main__":
    main()
