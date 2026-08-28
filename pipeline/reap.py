#!/usr/bin/env python3
"""Plan bounded deletion of superseded GitHub Release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


SAFE_CAP = 900
PROMO_HOURS = 72
SHARD = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])-[0-9a-f]{16}\.json\.gz$")
PROMO = re.compile(
    r"^(?:"
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-[0-9a-f]{16}\.json\.gz|"
    r"(?:index|ready)-[0-9a-f]{16}\.json|"
    r"(?:old|next)-(?:index|ready)-[0-9]+-[0-9]+-"
    r"(?:[0-9a-f]{1,16}|unknown)\.json"
    r")$"
)
PART = re.compile(r"^checkpoint-[0-9a-f]{16}-[0-9]{4}-[0-9a-f]{16}\.part$")
POINTER = re.compile(r"^pointer-[0-9]+-[0-9]+-[0-9a-f]{16}\.json$")


def read_json(path: Path) -> object:
    """Read one JSON value."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Release input is invalid: {path.name}") from error


def read_assets(path: Path) -> list[dict]:
    """Read a JSON array or one API object per line."""
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            value = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            raise ValueError("Release asset inventory is invalid") from error
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("Release asset inventory is unreadable") from error
    if not isinstance(value, list):
        raise ValueError("Release asset inventory is not a list")
    return value


def parse_time(value: object) -> datetime:
    """Parse one canonical GitHub UTC timestamp."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Release asset timestamp is invalid")
    try:
        result = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("Release asset timestamp is invalid") from error
    if result.utcoffset() != timedelta(0):
        raise ValueError("Release asset timestamp is invalid")
    return result


def check_assets(assets: object) -> list[dict]:
    """Require unique release assets with known states."""
    if not isinstance(assets, list):
        raise ValueError("Release assets are invalid")
    names = set()
    identifiers = set()
    for asset in assets:
        if (
            not isinstance(asset, dict)
            or not isinstance(asset.get("id"), int)
            or isinstance(asset.get("id"), bool)
            or asset["id"] < 1
            or not isinstance(asset.get("name"), str)
            or not asset["name"]
            or asset["name"] in names
            or asset["id"] in identifiers
            or asset.get("state", "uploaded") not in {"uploaded", "starter"}
        ):
            raise ValueError("Release assets are invalid")
        parse_time(asset.get("created_at"))
        names.add(asset["name"])
        identifiers.add(asset["id"])
    return assets


def file_hash(path: Path) -> str:
    """Return the digest for one pointer."""
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(f"Release pointer is unreadable: {path.name}") from error
    return hashlib.sha256(content).hexdigest()


def file_tag(path: Path) -> str:
    """Return the immutable short digest for one pointer."""
    return file_hash(path)[:16]


def promo_keep(index: Path, ready: Path) -> set[str]:
    """Return assets required by the current promoted snapshot."""
    value = read_json(index)
    shards = value.get("shards") if isinstance(value, dict) else None
    if not isinstance(shards, list) or not shards:
        raise ValueError("Promoted corpus index is invalid")
    paths = []
    for row in shards:
        name = row.get("path") if isinstance(row, dict) else None
        if not isinstance(name, str) or not SHARD.fullmatch(name):
            raise ValueError("Promoted corpus shard path is invalid")
        paths.append(name)
    if paths != sorted(set(paths)):
        raise ValueError("Promoted corpus shard paths are invalid")
    marker = read_json(ready)
    if not isinstance(marker, dict) or marker.get("index_sha256") != file_hash(index):
        raise ValueError("Promoted corpus readiness is invalid")
    return {
        *paths,
        "index.json",
        "cloud-ready.json",
        f"index-{file_tag(index)}.json",
        f"ready-{file_tag(ready)}.json",
    }


def make_plan(
    assets: object,
    required: set[str],
    managed,
    cutoff: datetime,
    reserve: int = 0,
) -> dict:
    """Delete only stale managed assets outside the required snapshot."""
    if reserve < 0:
        raise ValueError("Release asset reserve is invalid")
    rows = check_assets(assets)
    names = {row["name"] for row in rows if row.get("state", "uploaded") == "uploaded"}
    missing = sorted(required - names)
    if missing:
        raise ValueError(f"Required release assets are missing: {', '.join(missing)}")
    deleted = [
        row
        for row in rows
        if row["name"] not in required
        and managed.fullmatch(row["name"])
        and (
            row.get("state", "uploaded") == "starter"
            or parse_time(row["created_at"]) < cutoff
        )
    ]
    retained = len(rows) - len(deleted)
    if retained + reserve > SAFE_CAP:
        raise RuntimeError(
            f"Release needs {retained + reserve} assets after safe pruning; "
            f"cap is {SAFE_CAP}"
        )
    return {
        "delete": [row["id"] for row in deleted],
        "deleted": len(deleted),
        "retained": retained,
        "reserved": reserve,
        "required": len(required),
    }


def promo_plan(
    assets: object,
    index: Path,
    ready: Path,
    now: datetime,
    hours: int = PROMO_HOURS,
    reserve: int = 0,
) -> dict:
    """Bound corpus assets while protecting recent in-flight consumers."""
    if hours < 24 or now.utcoffset() != timedelta(0):
        raise ValueError("Promoted corpus retention is invalid")
    cutoff = now - timedelta(hours=hours)
    return make_plan(assets, promo_keep(index, ready), PROMO, cutoff, reserve)


def point_keep(assets: object, pointer: Path, current: str) -> set[str]:
    """Keep one complete checkpoint and its pointer."""
    value = read_json(pointer)
    parts = value.get("parts") if isinstance(value, dict) else None
    names = (
        [row.get("name") if isinstance(row, dict) else None for row in parts]
        if isinstance(parts, list)
        else None
    )
    if (
        not isinstance(names, list)
        or not names
        or names != sorted(set(names))
        or any(not isinstance(name, str) or not PART.fullmatch(name) for name in names)
        or not POINTER.fullmatch(current)
    ):
        raise ValueError("Checkpoint pointer is invalid")
    check_assets(assets)
    return {*names, current}


def point_plan(
    assets: object,
    pointer: Path,
    current: str,
    reserve: int = 0,
) -> dict:
    """Bound restart checkpoints to one complete generation."""
    required = point_keep(assets, pointer, current)
    managed = re.compile(f"(?:{PART.pattern}|{POINTER.pattern})")
    return make_plan(
        assets,
        required,
        managed,
        datetime.max.replace(tzinfo=timezone.utc),
        reserve,
    )


def parse_args() -> argparse.Namespace:
    """Parse one bounded release-retention plan."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("promo", "point"))
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--pointer", type=Path)
    parser.add_argument("--current")
    parser.add_argument("--hours", type=int, default=PROMO_HOURS)
    parser.add_argument("--reserve", type=int, default=0)
    parser.add_argument("--now")
    return parser.parse_args()


def main() -> None:
    """Print asset IDs that a workflow may safely delete."""
    args = parse_args()
    assets = read_assets(args.assets)
    if args.kind == "promo":
        if args.index is None or args.ready is None:
            raise SystemExit("promo requires --index and --ready")
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        plan = promo_plan(assets, args.index, args.ready, now, args.hours, args.reserve)
    else:
        if args.pointer is None or args.current is None:
            raise SystemExit("point requires --pointer and --current")
        plan = point_plan(assets, args.pointer, args.current, args.reserve)
    print(json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    main()
