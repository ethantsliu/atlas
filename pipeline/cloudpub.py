#!/usr/bin/env python3
"""Validate every committed semantic-cloud release asset without source caches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloudvec import MODEL_REVISION
from embed import MODEL, MODEL_DIGEST
from omit import ids_hash, read_cloud
from routes import ROUTE_COUNT, ROUTE_PAIR, check_routes
from pack import PACK_MODE, PACK_MONTHS, check_packs
from cloudaudit import SCOPES, meta_rows, point_rows, valid_asset


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "web/public/data/cloud"
DIGEST = set("0123456789abcdef")


def release_asset(output: Path, meta: object, expected: set[str], label: str) -> Path:
    """Resolve and authenticate one uniquely manifest-addressed release asset."""
    name = meta.get("path") if isinstance(meta, dict) else None
    if (
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or name in expected
    ):
        raise RuntimeError(f"Published cloud {label} path is invalid")
    path = output / name
    if not valid_asset(path, meta):
        raise RuntimeError(f"Published cloud {label} drifted")
    expected.add(name)
    return path


def count_map(value: object) -> bool:
    """Return whether one release count map is exact and non-negative."""
    return (
        isinstance(value, dict)
        and set(value) == set(SCOPES)
        and all(release_count(count) for count in value.values())
    )


def release_count(value: object) -> bool:
    """Return whether one manifest scalar is a non-negative integer."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def release_digest(value: object) -> bool:
    """Return whether one manifest digest is lowercase SHA-256."""
    return isinstance(value, str) and len(value) == 64 and set(value) <= DIGEST


def manifest_contract(cloud: dict) -> tuple[list[dict], int, str]:
    """Require the immutable top-level browser schema."""
    rows = cloud.get("shards")
    anchor_count = cloud.get("anchor_count")
    anchor_sha256 = cloud.get("anchor_sha256")
    if (
        cloud.get("source") != "arxiv"
        or cloud.get("model") != MODEL
        or cloud.get("model_digest") != MODEL_DIGEST
        or cloud.get("model_revision") != MODEL_REVISION
        or cloud.get("projection") != "anchor-cosine-8-v1"
        or cloud.get("point_bytes") != 13
        or cloud.get("relation") != "anchor-cosine-top8-v1"
        or cloud.get("route_bytes") != ROUTE_PAIR
        or cloud.get("neighbor_count") != ROUTE_COUNT
        or not release_count(anchor_count)
        or not ROUTE_COUNT <= anchor_count <= 65535
        or not release_digest(anchor_sha256)
        or not release_count(cloud.get("count"))
        or not release_count(cloud.get("source_count"))
        or not release_count(cloud.get("omitted_count"))
        or not count_map(cloud.get("counts"))
        or not count_map(cloud.get("omitted_counts"))
        or not release_digest(cloud.get("omitted_sha256"))
        or not release_digest(cloud.get("foreground_sha256"))
        or not isinstance(rows, list)
        or not rows
    ):
        raise RuntimeError("Published cloud manifest contract drifted")
    return rows, anchor_count, anchor_sha256


def validate_anchors(
    output: Path,
    cloud: dict,
    expected: set[str],
    anchor_count: int,
    anchor_sha256: str,
) -> None:
    """Validate the digest-bound anchor identity asset."""
    path = release_asset(output, cloud.get("anchors"), expected, "anchors")
    try:
        anchors = json.loads(path.read_text(encoding="utf-8"))
        identifiers = anchors["ids"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        raise RuntimeError("Published cloud anchor contract drifted") from error
    if (
        path.name != "anchors.json"
        or anchors.get("schema_version") != 1
        or anchors.get("model") != MODEL
        or anchors.get("model_digest") != MODEL_DIGEST
        or anchors.get("anchor_sha256") != anchor_sha256
        or anchors.get("count") != anchor_count
        or not isinstance(identifiers, list)
        or len(identifiers) != anchor_count
        or len(set(identifiers)) != anchor_count
        or any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        )
    ):
        raise RuntimeError("Published cloud anchor contract drifted")


def row_contract(row: object, anchor_sha256: str) -> tuple[str, list[str]]:
    """Require one shard's complete count and omission proof."""
    if not isinstance(row, dict):
        raise RuntimeError("Published cloud shard contract drifted")
    month = row.get("month")
    count = row.get("count")
    source_count = row.get("source_count")
    omitted_ids = row.get("omitted_ids")
    omitted_count = row.get("omitted_count")
    if (
        not isinstance(month, str)
        or len(month) != 7
        or month[4] != "-"
        or not month[:4].isdigit()
        or not month[5:].isdigit()
        or not 1 <= int(month[5:]) <= 12
        or not release_count(count)
        or not release_count(source_count)
        or source_count < count
        or not count_map(row.get("counts"))
        or not count_map(row.get("source_counts"))
        or not count_map(row.get("omitted_counts"))
        or not isinstance(omitted_ids, list)
        or omitted_ids != sorted(set(omitted_ids))
        or any(
            not isinstance(identifier, str) or not identifier
            for identifier in omitted_ids
        )
        or omitted_count != len(omitted_ids)
        or source_count != count + omitted_count
        or row.get("omitted_sha256") != ids_hash(omitted_ids)
        or row.get("anchor_sha256") != anchor_sha256
        or not release_digest(row.get("source_sha256"))
        or not release_digest(row.get("row_sha256"))
        or not release_digest(row.get("foreground_sha256"))
        or any(
            row["counts"][scope] + row["omitted_counts"][scope]
            != row["source_counts"][scope]
            for scope in SCOPES
        )
        or sum(row["counts"].values()) != count
        or sum(row["source_counts"].values()) != source_count
    ):
        raise RuntimeError(f"Published cloud shard contract drifted: {month}")
    return month, omitted_ids


def validate_published_assets(output: Path = OUTPUT_ROOT) -> dict:
    """Validate all referenced assets and reject unmanifested release files."""
    cloud = read_cloud(output / "index.json")
    rows, anchor_count, anchor_sha256 = manifest_contract(cloud)
    expected = {"index.json"}
    validate_anchors(output, cloud, expected, anchor_count, anchor_sha256)
    packed = (
        cloud.get("point_pack"),
        cloud.get("pack_months"),
        cloud.get("packs"),
    )
    months = []
    total_count = total_source = total_omitted = 0
    total_counts = {scope: 0 for scope in SCOPES}
    total_omitted_counts = {scope: 0 for scope in SCOPES}
    all_omitted = []
    for row in rows:
        month, omitted_ids = row_contract(row, anchor_sha256)
        months.append(month)
        points = release_asset(output, row.get("points"), expected, f"points {month}")
        metadata = release_asset(output, row.get("meta"), expected, f"metadata {month}")
        routes = release_asset(output, row.get("routes"), expected, f"routes {month}")
        if (
            points.name != f"{month}.bin"
            or metadata.name != f"{month}.json"
            or routes.name != f"{month}.routes"
        ):
            raise RuntimeError(f"Published cloud asset routing drifted: {month}")
        scopes = point_rows(points.read_bytes(), row, month)
        identifiers = meta_rows(
            metadata.read_text(encoding="utf-8"), row, scopes, month
        )
        if len(set(identifiers)) != row["count"] or set(identifiers).intersection(
            omitted_ids
        ):
            raise RuntimeError(f"Published cloud metadata coverage drifted: {month}")
        try:
            check_routes(
                routes.read_bytes(),
                row["count"],
                row["row_sha256"],
                anchor_count,
                anchor_sha256,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"Published cloud route contract drifted: {month}"
            ) from error
        total_count += row["count"]
        total_source += row["source_count"]
        total_omitted += row["omitted_count"]
        all_omitted.extend(omitted_ids)
        for scope in SCOPES:
            total_counts[scope] += row["counts"][scope]
            total_omitted_counts[scope] += row["omitted_counts"][scope]

    if packed != (None, None, None):
        if packed[0] != PACK_MODE or packed[1] != PACK_MONTHS:
            raise RuntimeError("Published cloud point packs drifted")
        check_packs(output, rows, packed[2])
        for pack in packed[2]:
            release_asset(output, pack.get("points"), expected, "point pack")

    actual = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    if (
        months != sorted(set(months))
        or cloud.get("count") != total_count
        or cloud.get("source_count") != total_source
        or cloud.get("omitted_count") != total_omitted
        or cloud.get("counts") != total_counts
        or cloud.get("omitted_counts") != total_omitted_counts
        or cloud.get("omitted_sha256") != ids_hash(all_omitted)
        or actual != expected
    ):
        raise RuntimeError("Published cloud release is incomplete")
    return cloud


def main() -> None:
    """Validate a committed release directory from the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    manifest = validate_published_assets(args.output)
    print(f"Validated {manifest['count']:,} published semantic points")


if __name__ == "__main__":
    main()
