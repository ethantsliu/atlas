#!/usr/bin/env python3
"""Run and preserve the official arXiv OAI corpus harvest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from archive import migrate_archive, write_manifest
from archivecheck import validate_archive
from dates import clean_date, coverage_day, exact_day, first_date
from files import atomic_write_text
from harvest import (
    HISTORY_START,
    advance_history,
    check_stage,
    check_history,
    gc_stages,
    plan_history,
    read_state,
    state_path,
)
from events import check_ledger
from merge import merge_generations, read_generation
from oai import OaiClient
from rank import load_rules
from resume import expiry_near, next_page, reset_stage, token_expired
from stage import scrub_stage


SCHEMA_VERSION = 1
DEFAULT_ROOT = Path("data/cache/corpus")
MAX_BYTES = 16 * 1024**3
MAX_FILES = 10_000


def utc_now() -> datetime:
    """Return an aware UTC wall-clock time."""
    return datetime.now(timezone.utc)


def cursor_path(root: Path) -> Path:
    """Return the durable corpus cursor path."""
    return root / "cursor.json"


def check_cursor(value: object) -> dict:
    """Validate the durable corpus-level cursor."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Corpus cursor contract is invalid")
    watermark = value.get("watermark")
    if watermark is not None:
        clean_date(watermark)
    coverage = exact_day(value.get("coverage_through_day"), "Corpus coverage")
    active = value.get("active")
    if active is not None and (
        not isinstance(active, dict)
        or not isinstance(active.get("generation"), str)
        or not active["generation"]
        or active.get("start") is not None
        and (not isinstance(active.get("start"), str) or not active["start"])
        or active.get("end") is not None
        and (not isinstance(active.get("end"), str) or not active["end"])
    ):
        raise ValueError("Corpus active generation is invalid")
    previous = value.get("last_generation")
    if previous is not None and (not isinstance(previous, str) or not previous):
        raise ValueError("Corpus prior generation is invalid")
    pending = value.get("pending", [])
    if (
        not isinstance(pending, list)
        or not all(isinstance(item, str) and item for item in pending)
        or len(pending) != len(set(pending))
    ):
        raise ValueError("Corpus pending generations are invalid")
    merged = value.get("merged", [])
    if (
        not isinstance(merged, list)
        or not all(isinstance(item, str) and item for item in merged)
        or len(merged) != len(set(merged))
        or any(item not in pending for item in merged)
    ):
        raise ValueError("Corpus merged generations are invalid")
    check_history(value.get("history"))
    return {
        **value,
        "coverage_through_day": coverage,
        "pending": pending,
        "merged": merged,
    }


def base_cursor(root: Path) -> dict:
    """Create a cursor whose first bounded window covers OAI history."""
    return {
        "schema_version": SCHEMA_VERSION,
        "watermark": None,
        "coverage_through_day": None,
        "active": None,
        "last_generation": None,
        "pending": [],
        "merged": [],
        "history": {
            "next_year": HISTORY_START,
            "through_year": None,
            "complete": False,
        },
    }


def read_cursor(root: Path) -> dict:
    """Read or recover the corpus-level cursor."""
    path = cursor_path(root)
    if not path.exists():
        return base_cursor(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Corpus cursor is unreadable") from error
    return check_cursor(value)


def write_cursor(root: Path, cursor: dict) -> None:
    """Atomically replace the corpus-level cursor."""
    check_cursor(cursor)
    atomic_write_text(
        cursor_path(root),
        json.dumps(cursor, ensure_ascii=False, indent=2) + "\n",
    )


def stage_refs(cursor: dict) -> set[str]:
    """Return raw stages still referenced by durable corpus state."""
    active = cursor.get("active")
    keep = set(cursor.get("pending", []))
    if active is not None:
        keep.add(active["generation"])
    return keep


def gen_name(root: Path, now: datetime) -> str:
    """Create a collision-free incremental generation name."""
    stem = f"sync-{now.astimezone(timezone.utc):%Y%m%dt%H%M%S}z"
    candidate = stem
    suffix = 1
    while state_path(root, candidate).exists():
        candidate = f"{stem}-{suffix}"
        suffix += 1
    return candidate


def plan_run(
    root: Path,
    now: datetime,
    *,
    batch: bool = False,
) -> tuple[dict, str, str | None, str | None]:
    """Select the bootstrap, resumed, or next incremental generation."""
    cursor = read_cursor(root)
    gc_stages(root, stage_refs(cursor))
    active = cursor["active"]
    if active is not None:
        write_cursor(root, cursor)
        return cursor, active["generation"], active["start"], active.get("end")
    if cursor["pending"] and (not batch or cursor["history"]["complete"]):
        raise RuntimeError(
            "Corpus pending generation must be promoted and acknowledged"
        )
    history = cursor["history"]
    if not history["complete"]:
        history, generation, start, end = plan_history(
            history, now.astimezone(timezone.utc).date()
        )
        cursor = {**cursor, "history": history}
    else:
        watermark = cursor["watermark"]
        if watermark is None:
            raise ValueError("Completed corpus history has no watermark")
        generation = gen_name(root, now)
        start = watermark[:10]
        end = None
    cursor = {
        **cursor,
        "active": {"generation": generation, "start": start, "end": end},
    }
    write_cursor(root, cursor)
    return cursor, generation, start, end


def finish_run(root: Path, cursor: dict, generation: str, manifest: dict) -> dict:
    """Advance an overlap-safe responseDate watermark after a sealed list."""
    watermark = first_date(manifest)
    prior = cursor.get("watermark")
    if prior is not None and watermark < prior:
        raise ValueError("Corpus watermark moved backwards")
    history = cursor["history"]
    if generation.startswith("history-"):
        history = advance_history(history, generation)
    result = {
        **cursor,
        "history": history,
        "watermark": watermark,
        "coverage_through_day": coverage_day(manifest, generation),
        "active": None,
        "last_generation": generation,
        "pending": [*cursor.get("pending", []), generation],
    }
    write_cursor(root, result)
    return result


def ack_pending(root: Path, generations: list[str]) -> dict:
    """Acknowledge generations only after their release is validated."""
    cursor = read_cursor(root)
    pending = cursor["pending"]
    merged = cursor["merged"]
    if (
        not generations
        or any(item not in pending for item in generations)
        or any(item not in merged for item in generations)
    ):
        raise ValueError("Corpus acknowledgement is not pending")
    for generation in generations:
        check_stage(root, generation)
        read_generation(root, generation)
    removed = set(generations)
    cursor = {
        **cursor,
        "pending": [item for item in pending if item not in removed],
        "merged": [item for item in merged if item not in removed],
    }
    write_cursor(root, cursor)
    gc_stages(root, stage_refs(cursor))
    return cursor


def merge_pending(root: Path, archive: Path, rules_path: Path) -> dict:
    """Merge every sealed, unpublished generation in source order."""
    cursor = read_cursor(root)
    rules = load_rules(rules_path)
    manifest = None
    remaining = [
        generation
        for generation in cursor["pending"]
        if generation not in cursor["merged"]
    ]
    if remaining:
        manifest = merge_generations(root, remaining, archive, rules)
        cursor = {**cursor, "merged": [*cursor["merged"], *remaining]}
        write_cursor(root, cursor)
    if manifest is None and (archive / "index.json").is_file():
        manifest = validate_archive(archive)
    return {
        "pending": cursor["pending"],
        "manifest": manifest,
    }


def read_json(path: Path) -> dict | None:
    """Read one optional JSON object."""
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Corpus JSON is unreadable: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Corpus JSON is not an object: {path.name}")
    return value


def prior_paths(prior: dict | None) -> dict[str, str]:
    """Validate prior promoted shard identities by month."""
    if prior is None:
        return {}
    shards = prior.get("shards")
    if prior.get("schema_version") != 1 or not isinstance(shards, list):
        raise ValueError("Prior promoted corpus index is invalid")
    result = {}
    for row in shards:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("month"), str)
            or not isinstance(row.get("path"), str)
            or row["month"] in result
        ):
            raise ValueError("Prior promoted corpus shard is invalid")
        result[row["month"]] = row["path"]
    return result


def prep_release(archive: Path, output: Path, prior_path: Path | None = None) -> dict:
    """Stage immutable shard assets and an atomic release index."""
    if output.exists() and any(output.iterdir()):
        raise ValueError("Corpus release staging directory is not empty")
    output.mkdir(parents=True, exist_ok=True)
    if migrate_archive(archive):
        write_manifest(archive)
    manifest = validate_archive(archive)
    prior = read_json(prior_path) if prior_path is not None else None
    old_paths = prior_paths(prior)
    shards = []
    assets = []
    months = []
    for row in manifest["shards"]:
        source = archive / row["path"]
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != row["sha256"]:
            raise ValueError(f"Corpus source shard drifted: {source.name}")
        name = f"{row['month']}-{digest[:16]}.json.gz"
        promoted = {**row, "path": name}
        shards.append(promoted)
        if old_paths.get(row["month"]) != name:
            shutil.copyfile(source, output / name)
            assets.append(name)
            months.append(row["month"])
    promoted = {**manifest, "shards": shards}
    atomic_write_text(
        output / "index.json",
        json.dumps(promoted, ensure_ascii=False, indent=2) + "\n",
    )
    keep = sorted(row["path"] for row in shards)
    plan = {
        "assets": assets,
        "months": months,
        "keep": keep,
        "index_sha256": hashlib.sha256(
            (output / "index.json").read_bytes()
        ).hexdigest(),
    }
    atomic_write_text(
        output / "plan.json",
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
    )
    return plan


def run_corpus(
    root: Path,
    client,
    *,
    max_pages: int,
    max_minutes: float,
    clock: Callable[[], float] = time.monotonic,
    wall: Callable[[], datetime] = utc_now,
    batch: bool = False,
) -> dict:
    """Harvest bounded pages while preserving a resumable checkpoint."""
    if max_pages < 1:
        raise ValueError("Corpus page limit must be positive")
    if max_minutes <= 0:
        raise ValueError("Corpus time limit must be positive")
    cursor, generation, start, end = plan_run(root, wall(), batch=batch)
    deadline = clock() + max_minutes * 60
    completed = 0
    reason = "page-limit"
    result = read_state(root, generation)
    prior_pages = result["page_count"] if result is not None else 0
    if token_expired(result, wall()):
        reset_stage(root, generation, result)
        result = None

    while completed < max_pages:
        if clock() >= deadline:
            reason = "time-limit"
            break
        if expiry_near(result, wall()):
            reason = "token-expiring"
            break
        before = result["page_count"] if result is not None else 0
        result, restarted = next_page(root, generation, client, start, end)
        if restarted:
            continue
        added = result["page_count"] - before
        if added not in {0, 1}:
            raise RuntimeError("Corpus single-page checkpoint advanced unexpectedly")
        completed += added
        if result["status"] == "complete":
            cursor = finish_run(root, cursor, generation, result)
            return {
                "status": "complete",
                "reason": "sealed",
                "generation": generation,
                "start": start,
                "end": end,
                "pages_this_run": completed,
                "prior_page_count": prior_pages,
                "page_count": result["page_count"],
                "record_count": result["record_count"],
                "watermark": cursor["watermark"],
            }
        if added == 0:
            raise RuntimeError("Corpus harvest made no progress")

    if result is None:
        result = read_state(root, generation)
    return {
        "status": "partial",
        "reason": reason,
        "generation": generation,
        "start": start,
        "end": end,
        "pages_this_run": completed,
        "prior_page_count": prior_pages,
        "page_count": result["page_count"] if result else 0,
        "record_count": result["record_count"] if result else 0,
        "watermark": result.get("watermark") if result else cursor["watermark"],
    }


def check_root(root: Path, *, archive: bool = True) -> dict:
    """Validate corpus state, optionally including the durable archive."""
    cursor = check_cursor(read_cursor(root))
    stage = root / "stage"
    generations = []
    states = {}
    if stage.exists():
        for path in sorted(item for item in stage.iterdir() if item.is_dir()):
            if (path / "state.json").exists():
                state = check_stage(root, path.name)
                states[path.name] = state
                generations.append(
                    {
                        "generation": path.name,
                        "status": state["status"],
                        "pages": state["page_count"],
                        "records": state["record_count"],
                    }
                )
    active = cursor.get("active")
    if active is not None and not any(
        row["generation"] == active["generation"] for row in generations
    ):
        if state_path(root, active["generation"]).exists():
            raise ValueError("Corpus active generation could not be validated")
    for generation in cursor["pending"]:
        state = states.get(generation)
        if state is None or state["status"] != "complete":
            raise ValueError("Corpus pending generation is not complete")
        read_generation(root, generation)
    archive_root = root / "archive"
    archive_report = (
        validate_archive(archive_root) if archive and archive_root.exists() else None
    )
    if archive_report is not None:
        check_ledger(archive_root, archive_report)
    return {
        "cursor": cursor,
        "generations": generations,
        "archive": archive_report,
    }


def pack_root(root: Path, archive: Path) -> None:
    """Package one validated checkpoint for durable release storage."""
    check_root(root)
    archive.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix="corpus-", suffix=".tar.gz", dir=archive.parent
    )
    os.close(handle)
    temporary = Path(name)
    try:
        with tarfile.open(temporary, "w:gz") as bundle:
            for path in sorted(root.rglob("*")):
                bundle.add(path, arcname=path.relative_to(root), recursive=False)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def safe_member(member: tarfile.TarInfo) -> None:
    """Reject unsafe or unexpectedly large checkpoint members."""
    path = PurePosixPath(member.name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not (member.isdir() or member.isreg())
        or member.size < 0
    ):
        raise ValueError("Corpus checkpoint contains an unsafe member")


def unpack_root(archive: Path, root: Path) -> None:
    """Restore and validate one release checkpoint."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("Corpus restore directory is not empty")
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if (
            len(members) > MAX_FILES
            or sum(member.size for member in members) > MAX_BYTES
        ):
            raise ValueError("Corpus checkpoint exceeds safe restore bounds")
        for member in members:
            safe_member(member)
        bundle.extractall(root, members=members)
    archive_root = root / "archive"
    if archive_root.exists() and migrate_archive(archive_root):
        write_manifest(archive_root)
    scrub_stages(root)
    check_root(root)


def scrub_stages(root: Path) -> list[str]:
    """Migrate every restored OAI stage before public checkpointing."""
    stage = root / "stage"
    if not stage.is_dir():
        return []
    return [
        path.name
        for path in sorted(stage.iterdir())
        if path.is_dir() and scrub_stage(root, path.name)
    ]


def parse_args() -> argparse.Namespace:
    """Parse the corpus command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="harvest a bounded official page set")
    run.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    run.add_argument("--max-pages", type=int, default=5_000)
    run.add_argument("--max-minutes", type=float, default=300)
    check = commands.add_parser("check", help="validate a checkpoint")
    check.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    check.add_argument(
        "--stage-only",
        action="store_true",
        help="validate the cursor and staged OAI pages without rescanning the archive",
    )
    pack = commands.add_parser("pack", help="package a checkpoint")
    pack.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    pack.add_argument("--archive", type=Path, required=True)
    unpack = commands.add_parser("unpack", help="restore a checkpoint")
    unpack.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    unpack.add_argument("--archive", type=Path, required=True)
    merge = commands.add_parser("merge", help="merge sealed OAI generations")
    merge.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    merge.add_argument("--archive", type=Path, required=True)
    merge.add_argument("--rules", type=Path, required=True)
    prep = commands.add_parser("prep", help="stage an atomic corpus release")
    prep.add_argument("--archive", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--prior", type=Path)
    ack = commands.add_parser("ack", help="acknowledge promoted generations")
    ack.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ack.add_argument("--generation", action="append", required=True)
    return parser.parse_args()


def main() -> None:
    """Run one corpus command."""
    args = parse_args()
    if args.command == "run":
        result = run_corpus(
            args.root,
            OaiClient(),
            max_pages=args.max_pages,
            max_minutes=args.max_minutes,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.command == "check":
        print(
            json.dumps(
                check_root(args.root, archive=not args.stage_only), sort_keys=True
            )
        )
    elif args.command == "pack":
        pack_root(args.root, args.archive)
    elif args.command == "unpack":
        unpack_root(args.archive, args.root)
    elif args.command == "merge":
        print(
            json.dumps(
                merge_pending(args.root, args.archive, args.rules), sort_keys=True
            )
        )
    elif args.command == "prep":
        print(
            json.dumps(
                prep_release(args.archive, args.output, args.prior), sort_keys=True
            )
        )
    else:
        print(json.dumps(ack_pending(args.root, args.generation), sort_keys=True))


if __name__ == "__main__":
    main()
