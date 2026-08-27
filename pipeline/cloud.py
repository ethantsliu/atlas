#!/usr/bin/env python3
"""Build compact semantic point shards for the historical arXiv swarm."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from archive import read_manifest, read_shard
from cloudvec import MODEL_REVISION, embed_records, row_hash as row_hash, worker_count
from embed import MODEL, MODEL_DIGEST
from files import atomic_write_bytes, atomic_write_text
from omit import (
    archive_text,
    cloud_cover,
    cloud_manifest,
    foreground_hash,
    ids_hash,
    load_foreground,
    read_cloud,
    reuse_bytes,
)
from routes import (
    ROUTE_COUNT,
    ROUTE_MAGIC,
    ROUTE_PAIR,
    anchor_bytes,
    check_routes,
    file_hash,
    load_anchors,
    load_node_ids,
    project_points,
    route_bytes,
    row_digest,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "data/cache/archive"
ANCHOR_PATH = ROOT / "data/source/anchors.npz"
CACHE_ROOT = ROOT / "data/cache/cloud"
OUTPUT_ROOT = ROOT / "web/public/data/cloud"
MAGIC = b"ATLASPT1"
SCOPES = {"likely": 0, "possible": 1, "outside": 2}


def parse_args() -> argparse.Namespace:
    """Parse archive point publication paths."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE_ROOT)
    parser.add_argument("--anchors", type=Path, default=ANCHOR_PATH)
    parser.add_argument("--cache", type=Path, default=CACHE_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    parser.add_argument(
        "--atlas", type=Path, default=ROOT / "web/public/data/atlas.json"
    )
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--provider", choices=("native", "ollama"), default="native")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=worker_count(),
    )
    return parser.parse_args()


def write_anchors(output: Path, ids: np.ndarray, anchor_sha256: str) -> dict:
    """Publish and describe one digest-bound anchor identity asset."""
    path = output / "anchors.json"
    atomic_write_bytes(path, anchor_bytes(ids, anchor_sha256))
    return asset_meta(path)


def point_bytes(points: np.ndarray, papers: list[dict]) -> bytes:
    """Encode coordinates and scope in a fixed-width browser buffer."""
    if points.shape != (len(papers), 3):
        raise ValueError("Archive point rows are misaligned")
    positions = np.ascontiguousarray(points, dtype="<f4").tobytes()
    scopes = bytes(SCOPES[paper["scope"]] for paper in papers)
    return struct.pack("<8sI", MAGIC, len(papers)) + positions + scopes


def meta_bytes(month: str, papers: list[dict]) -> bytes:
    """Encode hover metadata separately from the eager point cloud."""
    payload = {
        "schema_version": 1,
        "month": month,
        "count": len(papers),
        "papers": [
            [
                paper["id"],
                paper["title"],
                paper["url"],
                paper["published"],
                paper["scope"],
            ]
            for paper in papers
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def asset_meta(path: Path) -> dict:
    """Describe one immutable browser asset."""
    content = path.read_bytes()
    return {
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def valid_asset(path: Path, meta: object) -> bool:
    """Verify one prior browser asset before incremental reuse."""
    if not path.is_file() or not isinstance(meta, dict):
        return False
    content = path.read_bytes()
    return (
        meta.get("path") == path.name
        and meta.get("bytes") == len(content)
        and meta.get("sha256") == hashlib.sha256(content).hexdigest()
    )


def valid_row(output: Path, row: dict) -> bool:
    """Verify every row-addressed browser asset."""
    for key in ("points", "meta", "routes"):
        meta = row.get(key)
        path = output / meta.get("path", "") if isinstance(meta, dict) else output
        if not valid_asset(path, meta):
            return False
    return True


def write_month(
    month: str,
    source_sha: str,
    papers: list[dict],
    vectors: np.ndarray,
    anchors: tuple[np.ndarray, np.ndarray, np.ndarray],
    anchor_sha256: str,
    output: Path,
    coverage: dict | None = None,
) -> dict:
    """Publish one aligned point, metadata, and anchor-route set."""
    anchor_ids, anchor_vectors, anchor_points = anchors
    points, indexes, scores = project_points(
        vectors, anchor_vectors, anchor_points, ROUTE_COUNT
    )
    point_path = output / f"{month}.bin"
    meta_path = output / f"{month}.json"
    route_path = output / f"{month}.routes"
    atomic_write_bytes(point_path, point_bytes(points, papers))
    atomic_write_bytes(meta_path, meta_bytes(month, papers))
    atomic_write_bytes(
        route_path,
        route_bytes(
            indexes,
            scores,
            [paper["id"] for paper in papers],
            len(anchor_ids),
            anchor_sha256,
        ),
    )
    counts = {
        scope: sum(paper["scope"] == scope for paper in papers) for scope in SCOPES
    }
    row = {
        "month": month,
        "source_sha256": source_sha,
        "anchor_sha256": anchor_sha256,
        "row_sha256": row_digest([paper["id"] for paper in papers]),
        "count": len(papers),
        "counts": counts,
        "points": asset_meta(point_path),
        "meta": asset_meta(meta_path),
        "routes": asset_meta(route_path),
    }
    if coverage is not None:
        row.update(coverage)
    return row


def write_reused(
    month: str,
    source_sha: str,
    papers: list[dict],
    point_content: bytes,
    route_content: bytes,
    anchor_sha256: str,
    output: Path,
    coverage: dict,
) -> dict:
    """Publish filtered prior coordinates and routes with current metadata."""
    point_path = output / f"{month}.bin"
    meta_path = output / f"{month}.json"
    route_path = output / f"{month}.routes"
    atomic_write_bytes(point_path, point_content)
    atomic_write_bytes(meta_path, meta_bytes(month, papers))
    atomic_write_bytes(route_path, route_content)
    return {
        "month": month,
        "source_sha256": source_sha,
        "anchor_sha256": anchor_sha256,
        "row_sha256": row_digest([paper["id"] for paper in papers]),
        "count": len(papers),
        "counts": {
            scope: sum(paper["scope"] == scope for paper in papers) for scope in SCOPES
        },
        "points": asset_meta(point_path),
        "meta": asset_meta(meta_path),
        "routes": asset_meta(route_path),
        **coverage,
    }


def build_cloud(
    archive: Path,
    anchor_path: Path,
    cache: Path,
    output: Path,
    batch_size: int,
    workers: int = 1,
    provider: str = "native",
    foreground: dict[str, set[str]] | None = None,
    prior_root: Path | None = None,
    node_ids: set[str] | None = None,
) -> dict:
    """Incrementally build every locally available changed archive month."""
    source = read_manifest(archive)
    foreground = foreground or {}
    source_rows = {row["month"]: row for row in source["shards"]}
    preserve_prior = prior_root is not None
    prior_root = prior_root or output
    prior = read_cloud(prior_root / "index.json")
    shards = {row["month"]: row for row in prior["shards"]}
    anchor_sha256 = file_hash(anchor_path)
    anchors = load_anchors(anchor_path, node_ids)
    output.mkdir(parents=True, exist_ok=True)
    anchor_asset = write_anchors(output, anchors[0], anchor_sha256)
    for path in sorted(archive.glob("????-??.json.gz")):
        month = path.name.removesuffix(".json.gz")
        source_row = source_rows.get(month)
        if not source_row:
            raise RuntimeError(f"Archive index is missing {month}")
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if source_sha != source_row["sha256"]:
            raise RuntimeError(f"Archive shard digest is invalid: {month}")
        prior_row = shards.get(month)
        month_foreground = foreground.get(month, set())
        if (
            prior_row
            and prior_row.get("source_sha256") == source_sha
            and prior_row.get("anchor_sha256") == anchor_sha256
            and prior_row.get("foreground_sha256") == ids_hash(month_foreground)
        ):
            if valid_row(output, prior_row):
                continue
        payload = read_shard(path)
        papers, coverage = cloud_cover(payload["papers"], month_foreground)
        reused = reuse_bytes(
            prior_root,
            prior_row or {},
            [paper["id"] for paper in papers],
            MAGIC,
            None if preserve_prior else source_sha,
            ROUTE_MAGIC,
            ROUTE_COUNT * ROUTE_PAIR,
            anchor_sha256,
        )
        if reused is not None:
            shards[month] = write_reused(
                month,
                source_sha,
                papers,
                reused[0],
                reused[1],
                anchor_sha256,
                output,
                coverage,
            )
            continue
        records = [(paper["id"], archive_text(paper)) for paper in papers]
        vectors = embed_records(month, records, cache, batch_size, workers, provider)
        shards[month] = write_month(
            month,
            source_sha,
            papers,
            vectors,
            anchors,
            anchor_sha256,
            output,
            coverage,
        )
    missing = []
    for month, source_row in source_rows.items():
        row = shards.get(month)
        if row is None or row.get("source_sha256") != source_row.get("sha256"):
            missing.append(month)
            continue
        if not valid_row(output, row):
            missing.append(month)
    if missing:
        raise RuntimeError(
            f"Archive point shards are missing: {', '.join(sorted(missing))}"
        )
    ordered = [shards[month] for month in sorted(source_rows)]
    manifest = cloud_manifest(
        ordered,
        foreground,
        MODEL,
        MODEL_DIGEST,
        MODEL_REVISION,
        anchor_sha256,
        anchor_asset,
        len(anchors[0]),
        ROUTE_COUNT,
    )
    atomic_write_text(
        output / "index.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def validate_month(
    archive: Path,
    output: Path,
    source_row: dict,
    row: dict,
    candidates: set[str],
    anchor_sha256: str,
    anchor_count: int,
) -> None:
    """Validate one aligned physical-dedupe month and its omission proof."""
    month = source_row["month"]
    if row.get("source_sha256") != source_row.get("sha256"):
        raise RuntimeError(f"Archive cloud source drifted: {month}")
    if row.get("anchor_sha256") != anchor_sha256:
        raise RuntimeError(f"Archive cloud anchors drifted: {month}")
    if not valid_asset(output / row["points"]["path"], row.get("points")):
        raise RuntimeError(f"Archive cloud points drifted: {month}")
    if not valid_asset(output / row["meta"]["path"], row.get("meta")):
        raise RuntimeError(f"Archive cloud metadata drifted: {month}")
    if not valid_asset(output / row["routes"]["path"], row.get("routes")):
        raise RuntimeError(f"Archive cloud routes drifted: {month}")
    point_content = (output / row["points"]["path"]).read_bytes()
    magic, count = struct.unpack("<8sI", point_content[:12])
    if magic != MAGIC or count != row["count"] or len(point_content) != 12 + 13 * count:
        raise RuntimeError(f"Archive cloud point contract drifted: {month}")
    omitted_ids = row.get("omitted_ids")
    omitted_counts = row.get("omitted_counts")
    if (
        row.get("source_count") != source_row["counts"]["all"]
        or row.get("source_counts")
        != {scope: source_row["counts"][scope] for scope in SCOPES}
        or row.get("foreground_sha256") != ids_hash(candidates)
        or not isinstance(omitted_ids, list)
        or omitted_ids != sorted(set(omitted_ids))
        or any(identifier not in candidates for identifier in omitted_ids)
        or row.get("omitted_count") != len(omitted_ids)
        or row.get("omitted_sha256") != ids_hash(omitted_ids)
        or not isinstance(omitted_counts, dict)
        or set(omitted_counts) != set(SCOPES)
        or row["source_count"] != row["count"] + row["omitted_count"]
        or any(
            row["counts"][scope] + omitted_counts[scope] != source_row["counts"][scope]
            for scope in SCOPES
        )
    ):
        raise RuntimeError(f"Archive cloud omission proof drifted: {month}")
    meta = json.loads((output / row["meta"]["path"]).read_text(encoding="utf-8"))
    kept_ids = [paper[0] for paper in meta.get("papers", [])]
    expected_rows = row_digest(kept_ids)
    if (
        meta.get("count") != row["count"]
        or row.get("row_sha256") != expected_rows
        or len(kept_ids) != row["count"]
        or len(set(kept_ids) | set(omitted_ids)) != row["source_count"]
        or set(kept_ids).intersection(omitted_ids)
    ):
        raise RuntimeError(f"Archive cloud metadata coverage drifted: {month}")
    routes = (output / row["routes"]["path"]).read_bytes()
    try:
        check_routes(
            routes,
            row["count"],
            expected_rows,
            anchor_count,
            anchor_sha256,
        )
    except ValueError as error:
        raise RuntimeError(f"Archive cloud route contract drifted: {month}") from error
    source_path = archive / source_row["path"]
    if source_path.is_file():
        expected = sorted(
            paper["id"]
            for paper in read_shard(source_path)["papers"]
            if paper["id"] in candidates
        )
        if omitted_ids != expected:
            raise RuntimeError(f"Archive cloud omitted the wrong papers: {month}")


def validate_cloud(
    archive: Path,
    output: Path,
    foreground: dict[str, set[str]] | None = None,
    node_ids: set[str] | None = None,
) -> dict:
    """Require exact source coverage and self-verifying browser assets."""
    source = read_manifest(archive)
    foreground = foreground or {}
    cloud = read_cloud(output / "index.json")
    anchor_meta = cloud.get("anchors")
    anchor_path = (
        output / anchor_meta.get("path", "")
        if isinstance(anchor_meta, dict)
        else output
    )
    if not valid_asset(anchor_path, anchor_meta):
        raise RuntimeError("Archive cloud anchor identities drifted")
    try:
        anchor_data = json.loads(anchor_path.read_text(encoding="utf-8"))
        anchor_ids = anchor_data["ids"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        raise RuntimeError("Archive cloud anchor identities drifted") from error
    anchor_sha256 = cloud.get("anchor_sha256")
    anchor_count = cloud.get("anchor_count")
    if (
        cloud.get("relation") != "anchor-cosine-top8-v1"
        or cloud.get("route_bytes") != ROUTE_PAIR
        or cloud.get("neighbor_count") != ROUTE_COUNT
        or not isinstance(anchor_sha256, str)
        or len(anchor_sha256) != 64
        or anchor_data.get("schema_version") != 1
        or anchor_data.get("model") != MODEL
        or anchor_data.get("model_digest") != MODEL_DIGEST
        or anchor_data.get("anchor_sha256") != anchor_sha256
        or not isinstance(anchor_count, int)
        or isinstance(anchor_count, bool)
        or not ROUTE_COUNT <= anchor_count <= 65535
        or anchor_data.get("count") != anchor_count
        or not isinstance(anchor_ids, list)
        or len(anchor_ids) != anchor_count
        or len(set(anchor_ids)) != anchor_count
        or any(
            not isinstance(identifier, str) or not identifier
            for identifier in anchor_ids
        )
        or (node_ids is not None and set(anchor_ids) != node_ids)
    ):
        raise RuntimeError("Archive cloud anchor identities drifted")
    source_rows = {row["month"]: row for row in source["shards"]}
    cloud_rows = {row["month"]: row for row in cloud["shards"]}
    if list(source_rows) != sorted(source_rows) or list(cloud_rows) != sorted(
        cloud_rows
    ):
        raise RuntimeError("Archive cloud months are not ordered")
    if set(source_rows) != set(cloud_rows):
        raise RuntimeError("Archive cloud does not exactly cover its source")
    for month, row in cloud_rows.items():
        validate_month(
            archive,
            output,
            source_rows[month],
            row,
            foreground.get(month, set()),
            anchor_sha256,
            anchor_count,
        )
    all_omitted = [
        identifier for row in cloud_rows.values() for identifier in row["omitted_ids"]
    ]
    if (
        cloud.get("source_count") != source.get("counts", {}).get("all")
        or cloud.get("count") + cloud.get("omitted_count", -1)
        != cloud.get("source_count")
        or cloud.get("omitted_count") != len(all_omitted)
        or cloud.get("omitted_sha256") != ids_hash(all_omitted)
        or cloud.get("foreground_sha256") != foreground_hash(foreground)
        or cloud.get("counts")
        != {
            scope: sum(row["counts"][scope] for row in cloud_rows.values())
            for scope in SCOPES
        }
        or cloud.get("omitted_counts")
        != {
            scope: sum(row["omitted_counts"][scope] for row in cloud_rows.values())
            for scope in SCOPES
        }
        or any(
            cloud["counts"][scope] + cloud["omitted_counts"][scope]
            != source["counts"][scope]
            for scope in SCOPES
        )
    ):
        raise RuntimeError("Archive cloud total does not match its source")
    return cloud


def main() -> None:
    """Build the historical semantic point cloud."""
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    if args.check:
        manifest = validate_cloud(
            args.archive,
            args.output,
            load_foreground(args.atlas),
            load_node_ids(args.atlas),
        )
        print(f"Validated {manifest['count']:,} historical semantic points")
    else:
        manifest = build_cloud(
            args.archive,
            args.anchors,
            args.cache,
            args.output,
            args.batch_size,
            args.workers,
            args.provider,
            load_foreground(args.atlas),
            args.prior,
            load_node_ids(args.atlas),
        )
        print(f"Published {manifest['count']:,} historical semantic points")


if __name__ == "__main__":
    main()
