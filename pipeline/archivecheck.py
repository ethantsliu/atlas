#!/usr/bin/env python3
"""Validate the resumable arXiv archive index and available month shards."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from archive import ARCHIVE_ROOT, SCOPES, read_manifest, shard_meta


def check(value: bool, message: str) -> None:
    """Raise one actionable archive contract failure."""
    if not value:
        raise RuntimeError(message)


def valid_date(value: object, month: str) -> bool:
    """Accept one ISO day that belongs to its declared shard month."""
    try:
        return (
            isinstance(value, str)
            and date.fromisoformat(value).strftime("%Y-%m") == month
        )
    except ValueError:
        return False


def validate_archive(root: Path = ARCHIVE_ROOT) -> dict:
    """Verify global counts, dates, ordering, and each available shard hash."""
    manifest = read_manifest(root)
    shards = manifest["shards"]
    months = [shard.get("month") for shard in shards]
    check(months == sorted(set(months)), "Archive months are duplicated or unsorted")
    seen: set[str] = set()
    totals = {key: 0 for key in ("all", *SCOPES)}
    for shard in shards:
        month = shard["month"]
        counts = shard.get("counts", {})
        check(
            all(isinstance(counts.get(key), int) for key in totals),
            f"Archive counts are invalid for {month}",
        )
        check(
            counts["all"] == sum(counts[scope] for scope in SCOPES),
            f"Archive scope counts do not cover {month}",
        )
        dates = shard.get("dates", [])
        check(
            len(dates) == shard.get("days") == len(set(dates)),
            f"Archive date proof is invalid for {month}",
        )
        check(
            all(valid_date(value, month) for value in dates),
            f"Archive date belongs to another month: {month}",
        )
        check(not seen.intersection(dates), f"Archive dates overlap at {month}")
        seen.update(dates)
        for key in totals:
            totals[key] += counts[key]
        path = root / shard.get("path", "")
        if path.is_file():
            check(shard_meta(path) == shard, f"Archive shard drifted: {path.name}")
    check(manifest.get("counts") == totals, "Archive global counts are stale")
    return manifest


def main() -> None:
    """Validate the default archive and print its retained record count."""
    manifest = validate_archive()
    print(f"Validated {manifest['counts']['all']:,} archived arXiv records")


if __name__ == "__main__":
    main()
