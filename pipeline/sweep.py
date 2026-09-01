#!/usr/bin/env python3
"""Harvest bounded OAI years serially and attach sealed stages safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from corpus import check_cursor, read_cursor, write_cursor
from harvest import (
    HISTORY_FIRST,
    HISTORY_START,
    advance_history,
    check_stage,
    run_harvest,
    stage_path,
)
from merge import read_generation
from oai import OaiClient


def utc_day() -> date:
    """Return the current UTC calendar day."""
    return datetime.now(timezone.utc).date()


def clean_year(value: int, field: str) -> int:
    """Require one supported four-digit year."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 2005 <= value <= 9999
    ):
        raise ValueError(f"Sweep {field} year is invalid")
    return value


def year_span(first: int, last: int, through: date) -> list[tuple[int, str, str]]:
    """Build contiguous inclusive annual datestamp windows."""
    first = clean_year(first, "start")
    last = clean_year(last, "end")
    if not isinstance(through, date) or isinstance(through, datetime):
        raise ValueError("Sweep through date is invalid")
    if first > last or last > through.year:
        raise ValueError("Sweep year range is invalid")
    return [
        (
            year,
            HISTORY_FIRST if year == HISTORY_START else f"{year:04d}-01-01",
            through.isoformat() if year == through.year else f"{year:04d}-12-31",
        )
        for year in range(first, last + 1)
    ]


def check_query(manifest: dict, start: str, end: str) -> None:
    """Require the exact bounded query for one sealed stage."""
    query = manifest.get("query")
    if (
        not isinstance(query, dict)
        or query.get("from") != start
        or query.get("until") != end
    ):
        raise ValueError("Sweep stage query does not match its year")


def check_span(root: Path, first: int, last: int, through: date) -> list[dict]:
    """Validate every expected sealed stage in source order."""
    manifests = []
    for year, start, end in year_span(first, last, through):
        generation = f"history-{year}"
        state = check_stage(root, generation)
        if state["status"] != "complete":
            raise ValueError("Sweep stage is incomplete")
        manifest = read_generation(root, generation)
        check_query(manifest, start, end)
        manifests.append(manifest)
    return manifests


def source_root(source: Path) -> Path:
    """Resolve one direct or artifact-wrapped sweep root."""
    if source.is_symlink():
        raise ValueError("Sweep source root is unsafe")
    roots = [source, source / "arxiv-sweep"]
    found = []
    for root in roots:
        stage = root / "stage"
        if not stage.exists():
            continue
        if root.is_symlink() or stage.is_symlink() or not stage.is_dir():
            raise ValueError("Sweep source stage is invalid")
        found.append(root)
    if len(found) != 1:
        raise ValueError("Sweep source has no unique stage")
    return found[0]


def harvest_span(
    root: Path,
    first: int,
    last: int,
    through: date,
    client=None,
) -> dict:
    """Harvest and seal annual windows through one reused client."""
    client = client or OaiClient()
    for year, start, end in year_span(first, last, through):
        result = run_harvest(
            root,
            f"history-{year}",
            client,
            start=start,
            end=end,
        )
        if result.get("status") != "complete" or result.get("sealed") is not True:
            raise ValueError("Sweep stage did not seal")
    manifests = check_span(root, first, last, through)
    return {
        "status": "complete",
        "start_year": first,
        "end_year": last,
        "through": through.isoformat(),
        "generations": [manifest["generation"] for manifest in manifests],
        "records": sum(manifest["record_count"] for manifest in manifests),
    }


def tree_hash(root: Path) -> str:
    """Hash one regular-file tree including its relative paths."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Sweep stage contains an unsafe member")
        relative = path.relative_to(root).as_posix().encode()
        digest.update(b"d\0" if path.is_dir() else b"f\0")
        digest.update(relative)
        digest.update(b"\0")
        if path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def check_clean(cursor: dict, first: int, last: int) -> None:
    """Require a promotion-clean cursor immediately before the range."""
    history = cursor["history"]
    expected = f"history-{first - 1}"
    if (
        cursor["active"] is not None
        or cursor["pending"]
        or cursor["merged"]
        or cursor.get("last_generation") != expected
        or history["next_year"] != first
        or history["complete"]
        or history["through_year"] is None
        or last > history["through_year"]
    ):
        raise ValueError("Corpus cursor is not clean before the sweep")


def history_year(generation: str) -> int:
    """Read one canonical annual generation name."""
    if not generation.startswith("history-"):
        raise ValueError("Corpus pending generation is not annual history")
    try:
        year = int(generation.removeprefix("history-"))
    except ValueError as error:
        raise ValueError("Corpus pending history year is invalid") from error
    return clean_year(year, "pending")


def check_prefix(cursor: dict, first: int, last: int) -> None:
    """Require a complete later range that the sweep immediately precedes."""
    history = cursor["history"]
    years = [history_year(generation) for generation in cursor["pending"]]
    if (
        cursor["active"] is not None
        or cursor["merged"]
        or not years
        or years != list(range(last + 1, history["through_year"] + 1))
        or first != HISTORY_START
        or history["next_year"] != history["through_year"] + 1
        or not history["complete"]
        or cursor.get("last_generation") != f"history-{history['through_year']}"
        or not isinstance(cursor.get("watermark"), str)
        or not cursor.get("coverage_through_day")
    ):
        raise ValueError("Corpus cursor is not complete after the sweep prefix")


def prefix_cursor(cursor: dict, manifests: list[dict]) -> dict:
    """Prepend sealed missing years without weakening later coverage."""
    generations = [manifest["generation"] for manifest in manifests]
    watermarks = [
        manifest["pages"][0].get("response_date")
        for manifest in manifests
        if manifest.get("pages")
    ]
    if len(watermarks) != len(manifests) or not all(
        isinstance(value, str) for value in watermarks
    ):
        raise ValueError("Sweep stage has no response watermark")
    watermark = max([cursor["watermark"], *watermarks])
    return check_cursor(
        {
            **cursor,
            "watermark": watermark,
            "pending": [*generations, *cursor["pending"]],
        }
    )


def next_cursor(cursor: dict, manifests: list[dict]) -> dict:
    """Build one atomic cursor update for attached history stages."""
    result = cursor
    for manifest in manifests:
        generation = manifest["generation"]
        pages = manifest.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("Sweep stage has no response watermark")
        watermark = pages[0].get("response_date")
        prior = result.get("watermark")
        if not isinstance(watermark, str) or prior is not None and watermark < prior:
            raise ValueError("Sweep response watermark moved backwards")
        result = {
            **result,
            "watermark": watermark,
            "last_generation": generation,
            "pending": [*result["pending"], generation],
            "history": advance_history(result["history"], generation),
        }
    return check_cursor(result)


def check_targets(source: Path, target: Path, manifests: list[dict]) -> None:
    """Reject every destination collision before copying anything."""
    for manifest in manifests:
        generation = manifest["generation"]
        origin = stage_path(source, generation)
        destination = stage_path(target, generation)
        tree_hash(origin)
        if not destination.exists():
            continue
        read_generation(target, generation)
        if tree_hash(origin) != tree_hash(destination):
            raise ValueError(f"Corpus stage collision: {generation}")


def copy_stage(source: Path, target: Path, generation: str) -> bool:
    """Install one validated stage by same-filesystem atomic rename."""
    origin = stage_path(source, generation)
    destination = stage_path(target, generation)
    if destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sweep-", dir=destination.parent) as folder:
        temporary = Path(folder) / generation
        shutil.copytree(origin, temporary)
        if tree_hash(origin) != tree_hash(temporary):
            raise ValueError("Copied sweep stage failed verification")
        os.replace(temporary, destination)
    read_generation(target, generation)
    return True


def attach_span(
    source: Path,
    target: Path,
    first: int,
    last: int,
    through: date,
) -> dict:
    """Attach validated stages and atomically advance a clean cursor."""
    source = source_root(source)
    if source.resolve() == target.resolve():
        raise ValueError("Sweep source and corpus root must differ")
    manifests = check_span(source, first, last, through)
    cursor = read_cursor(target)
    try:
        check_clean(cursor, first, last)
    except ValueError:
        check_prefix(cursor, first, last)
        mode = "prefix"
        updated = prefix_cursor(cursor, manifests)
    else:
        mode = "forward"
        updated = next_cursor(cursor, manifests)
        updated = check_cursor(
            {
                **updated,
                "watermark": f"{through.isoformat()}T00:00:00Z",
                "coverage_through_day": through.isoformat(),
            }
        )
    check_targets(source, target, manifests)
    copied = [
        manifest["generation"]
        for manifest in manifests
        if copy_stage(source, target, manifest["generation"])
    ]
    write_cursor(target, updated)
    return {
        "status": "attached",
        "mode": mode,
        "generations": [manifest["generation"] for manifest in manifests],
        "copied": copied,
        "pending": updated["pending"],
    }


def parse_day(value: str) -> date:
    """Parse one canonical calendar day."""
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("through must use YYYY-MM-DD") from error
    if result.isoformat() != value:
        raise argparse.ArgumentTypeError("through must use YYYY-MM-DD")
    return result


def add_range(parser: argparse.ArgumentParser) -> None:
    """Add the shared explicit year-range arguments."""
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--through", type=parse_day, default=utc_day())


def parse_args() -> argparse.Namespace:
    """Parse the sweep command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    harvest = commands.add_parser("harvest", help="harvest sealed annual stages")
    harvest.add_argument("--root", type=Path, required=True)
    add_range(harvest)
    attach = commands.add_parser("attach", help="attach stages to a corpus checkpoint")
    attach.add_argument("--source", type=Path, required=True)
    attach.add_argument("--root", type=Path, required=True)
    add_range(attach)
    return parser.parse_args()


def main() -> None:
    """Run one sweep command."""
    args = parse_args()
    if args.command == "harvest":
        result = harvest_span(
            args.root,
            args.start_year,
            args.end_year,
            args.through,
        )
    else:
        result = attach_span(
            args.source,
            args.root,
            args.start_year,
            args.end_year,
            args.through,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
