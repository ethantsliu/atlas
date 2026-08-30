#!/usr/bin/env python3
"""Harvest consecutive arXiv history windows in one restored checkpoint."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, time as day_time, timedelta, timezone
from pathlib import Path
from typing import Callable

from corpus import DEFAULT_ROOT, read_cursor, run_corpus, utc_now
from oai import OaiClient

TOKEN_MARGIN = timedelta(minutes=90)


def token_delay(now: datetime) -> float:
    """Wait near UTC rollover instead of starting a doomed long token walk."""
    if now.tzinfo is None:
        raise ValueError("Corpus batch time must be timezone-aware")
    current = now.astimezone(timezone.utc)
    reset = datetime.combine(
        current.date() + timedelta(days=1),
        day_time(minute=1),
        tzinfo=timezone.utc,
    )
    remaining = reset - current
    return remaining.total_seconds() if remaining <= TOKEN_MARGIN else 0


def run_batch(
    root: Path,
    client,
    *,
    max_pages: int,
    max_minutes: float,
    clock: Callable[[], float] = time.monotonic,
    wall: Callable[[], datetime] = utc_now,
) -> dict:
    """Harvest consecutive history windows inside one restored checkpoint."""
    if max_pages < 1:
        raise ValueError("Corpus page limit must be positive")
    if max_minutes <= 0:
        raise ValueError("Corpus time limit must be positive")
    started = clock()
    pages = 0
    results = []
    while pages < max_pages:
        minutes = max_minutes - (clock() - started) / 60
        if minutes <= 0:
            break
        result = run_corpus(
            root,
            client,
            max_pages=max_pages - pages,
            max_minutes=minutes,
            clock=clock,
            wall=wall,
            batch=True,
        )
        results.append(result)
        pages += result["pages_this_run"]
        cursor = read_cursor(root)
        if result["status"] != "complete" or cursor["history"]["complete"]:
            break
    if not results:
        raise RuntimeError("Corpus batch exhausted its time before harvesting")
    return {
        **results[-1],
        "batch_generations": [row["generation"] for row in results],
        "batch_pages": pages,
    }


def parse_args() -> argparse.Namespace:
    """Parse the bounded batch command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--max-pages", type=int, default=5_000)
    parser.add_argument("--max-minutes", type=float, default=300)
    return parser.parse_args()


def main() -> None:
    """Run one bounded multi-window harvest."""
    args = parse_args()
    delay = token_delay(utc_now())
    if delay:
        print(f"Waiting {delay / 60:.1f} minutes for a fresh OAI token day", flush=True)
        time.sleep(delay)
    result = run_batch(
        args.root,
        OaiClient(),
        max_pages=args.max_pages,
        max_minutes=args.max_minutes,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
