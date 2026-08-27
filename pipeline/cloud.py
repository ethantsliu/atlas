#!/usr/bin/env python3
"""Build compact semantic point shards for the historical arXiv swarm."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from archive import read_manifest, read_shard
from embed import EMBED_DIM, MODEL, MODEL_DIGEST, embed_batch, verify_model
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


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "data/cache/archive"
ANCHOR_PATH = ROOT / "data/source/anchors.npz"
CACHE_ROOT = ROOT / "data/cache/cloud"
OUTPUT_ROOT = ROOT / "web/public/data/cloud"
MAGIC = b"ATLASPT1"
SCOPES = {"likely": 0, "possible": 1, "outside": 2}
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
_NATIVE = None


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
        default=max(1, int(os.getenv("ATLAS_EMBED_WORKERS", "1"))),
    )
    return parser.parse_args()


def row_hash(identifier: str, text: str) -> str:
    """Bind one reusable vector to its paper text and pinned model."""
    body = json.dumps(
        {
            "schema": "archive-vector-v1",
            "model": MODEL,
            "digest": MODEL_DIGEST,
            "native_model": MODEL_ID,
            "native_revision": MODEL_REVISION,
            "id": identifier,
            "text": text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(body).hexdigest()


def load_anchors(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load normalized vectors and fixed coordinates from a portable bundle."""
    with np.load(path) as bundle:
        vectors = np.asarray(bundle["vectors"], dtype=np.float32)
        points = np.asarray(bundle["points"], dtype=np.float32)
        model = str(bundle["model"])
        digest = str(bundle["model_digest"])
        dimensions = int(bundle["dimensions"])
    if (
        vectors.ndim != 2
        or vectors.shape[1] != EMBED_DIM
        or points.shape != (len(vectors), 3)
        or model != MODEL
        or digest != MODEL_DIGEST
        or dimensions != EMBED_DIM
        or not np.isfinite(vectors).all()
        or not np.isfinite(points).all()
    ):
        raise RuntimeError("Archive semantic anchors are invalid")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("Archive semantic anchors contain zero vectors")
    return vectors / norms, points


def load_cache(
    path: Path, records: list[tuple[str, str]], hashes: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Reuse unchanged rows from a resumable monthly vector cache."""
    vectors = np.zeros((len(records), EMBED_DIM), dtype=np.float32)
    done = np.zeros(len(records), dtype=bool)
    if not path.exists():
        return vectors, done
    try:
        with np.load(path) as cached:
            ids = np.asarray(cached["ids"]).astype(str)
            saved_hashes = np.asarray(cached["hashes"]).astype(str)
            saved = np.asarray(cached["vectors"], dtype=np.float32)
        if len(ids) != len(saved_hashes) or saved.shape != (len(ids), EMBED_DIM):
            return vectors, done
        indexes = {identifier: index for index, identifier in enumerate(ids)}
        for index, (identifier, _) in enumerate(records):
            saved_index = indexes.get(identifier)
            if (
                saved_index is not None
                and saved_hashes[saved_index] == hashes[index]
                and np.isfinite(saved[saved_index]).all()
                and np.linalg.norm(saved[saved_index]) > 0
            ):
                vectors[index] = saved[saved_index]
                done[index] = True
    except (OSError, ValueError, KeyError):
        pass
    return vectors, done


def save_cache(
    path: Path,
    records: list[tuple[str, str]],
    hashes: np.ndarray,
    vectors: np.ndarray,
    done: np.ndarray,
) -> None:
    """Checkpoint a monthly embedding batch atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npz")
    np.savez(
        temporary,
        ids=np.asarray([identifier for identifier, _ in records]),
        hashes=hashes,
        vectors=vectors,
        done=done,
    )
    temporary.replace(path)


def native_batch(texts: list[str]) -> np.ndarray:
    """Embed a large batch with the exact upstream MiniLM revision."""
    global _NATIVE
    if _NATIVE is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError("Native archive embedding requires cloud.txt") from error
        _NATIVE = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION)
    return np.asarray(
        _NATIVE.encode(
            texts,
            batch_size=256,
            show_progress_bar=False,
            normalize_embeddings=True,
        ),
        dtype=np.float32,
    )


def embed_records(
    month: str,
    records: list[tuple[str, str]],
    root: Path,
    batch_size: int,
    workers: int = 1,
    provider: str = "native",
) -> np.ndarray:
    """Embed one month with a row-addressable resumable checkpoint."""
    path = root / f"{month}.npz"
    hashes = np.asarray([row_hash(*record) for record in records])
    vectors, done = load_cache(path, records, hashes)
    pending = np.flatnonzero(~done)
    if len(pending) and provider == "ollama":
        verify_model()
    batches = [
        pending[start : start + batch_size]
        for start in range(0, len(pending), batch_size)
    ]

    def embed_rows(indexes: np.ndarray) -> np.ndarray:
        texts = [records[int(index)][1] for index in indexes]
        if provider == "native":
            return native_batch(texts)
        return np.asarray(embed_batch(texts), dtype=np.float32)

    def save_result(indexes: np.ndarray, result: np.ndarray) -> None:
        if result.shape != (len(indexes), EMBED_DIM):
            raise RuntimeError("Archive embedding batch has an invalid shape")
        vectors[indexes] = result
        done[indexes] = True
        save_cache(path, records, hashes, vectors, done)
        print(
            f"Embedded {month}: {int(done.sum()):,}/{len(records):,}",
            flush=True,
        )

    if provider == "native":
        for indexes in batches:
            save_result(indexes, embed_rows(indexes))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for indexes, result in zip(
                batches, executor.map(embed_rows, batches), strict=True
            ):
                save_result(indexes, result)
    return vectors


def project_points(
    vectors: np.ndarray,
    anchors: np.ndarray,
    points: np.ndarray,
    neighbors: int = 8,
) -> np.ndarray:
    """Interpolate fixed anchor coordinates from exact cosine neighbors."""
    if len(vectors) == 0:
        return np.empty((0, 3), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("Archive embeddings contain zero vectors")
    normalized = vectors / norms
    output = np.empty((len(vectors), 3), dtype=np.float32)
    count = min(neighbors, len(anchors))
    for start in range(0, len(vectors), 1024):
        stop = min(start + 1024, len(vectors))
        scores = normalized[start:stop] @ anchors.T
        indexes = np.argpartition(scores, -count, axis=1)[:, -count:]
        near = np.take_along_axis(scores, indexes, axis=1)
        weights = np.exp((near - near.max(axis=1, keepdims=True)) * 18)
        weights /= weights.sum(axis=1, keepdims=True)
        output[start:stop] = np.sum(points[indexes] * weights[..., None], axis=1)
    if not np.isfinite(output).all():
        raise RuntimeError("Archive semantic projection is invalid")
    return output


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


def write_month(
    month: str,
    source_sha: str,
    papers: list[dict],
    vectors: np.ndarray,
    anchors: tuple[np.ndarray, np.ndarray],
    output: Path,
    coverage: dict | None = None,
) -> dict:
    """Publish one aligned point and metadata pair."""
    points = project_points(vectors, *anchors)
    point_path = output / f"{month}.bin"
    meta_path = output / f"{month}.json"
    atomic_write_bytes(point_path, point_bytes(points, papers))
    atomic_write_bytes(meta_path, meta_bytes(month, papers))
    counts = {
        scope: sum(paper["scope"] == scope for paper in papers) for scope in SCOPES
    }
    row = {
        "month": month,
        "source_sha256": source_sha,
        "count": len(papers),
        "counts": counts,
        "points": asset_meta(point_path),
        "meta": asset_meta(meta_path),
    }
    if coverage is not None:
        row.update(coverage)
    return row


def write_reused(
    month: str,
    source_sha: str,
    papers: list[dict],
    content: bytes,
    output: Path,
    coverage: dict,
) -> dict:
    """Publish filtered prior coordinates with current aligned metadata."""
    point_path = output / f"{month}.bin"
    meta_path = output / f"{month}.json"
    atomic_write_bytes(point_path, content)
    atomic_write_bytes(meta_path, meta_bytes(month, papers))
    return {
        "month": month,
        "source_sha256": source_sha,
        "count": len(papers),
        "counts": {
            scope: sum(paper["scope"] == scope for paper in papers) for scope in SCOPES
        },
        "points": asset_meta(point_path),
        "meta": asset_meta(meta_path),
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
) -> dict:
    """Incrementally build every locally available changed archive month."""
    source = read_manifest(archive)
    foreground = foreground or {}
    source_rows = {row["month"]: row for row in source["shards"]}
    preserve_prior = prior_root is not None
    prior_root = prior_root or output
    prior = read_cloud(prior_root / "index.json")
    shards = {row["month"]: row for row in prior["shards"]}
    anchors = load_anchors(anchor_path)
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
            and prior_row.get("foreground_sha256") == ids_hash(month_foreground)
        ):
            point_path = output / prior_row["points"]["path"]
            meta_path = output / prior_row["meta"]["path"]
            if valid_asset(point_path, prior_row.get("points")) and valid_asset(
                meta_path, prior_row.get("meta")
            ):
                continue
        payload = read_shard(path)
        papers, coverage = cloud_cover(payload["papers"], month_foreground)
        reused = reuse_bytes(
            prior_root,
            prior_row or {},
            [paper["id"] for paper in papers],
            MAGIC,
            None if preserve_prior else source_sha,
        )
        if reused is not None:
            shards[month] = write_reused(
                month, source_sha, papers, reused, output, coverage
            )
            continue
        records = [(paper["id"], archive_text(paper)) for paper in papers]
        vectors = embed_records(month, records, cache, batch_size, workers, provider)
        shards[month] = write_month(
            month, source_sha, papers, vectors, anchors, output, coverage
        )
    missing = []
    for month, source_row in source_rows.items():
        row = shards.get(month)
        if row is None or row.get("source_sha256") != source_row.get("sha256"):
            missing.append(month)
            continue
        if not valid_asset(output / row["points"]["path"], row.get("points")):
            missing.append(month)
            continue
        if not valid_asset(output / row["meta"]["path"], row.get("meta")):
            missing.append(month)
    if missing:
        raise RuntimeError(
            f"Archive point shards are missing: {', '.join(sorted(missing))}"
        )
    ordered = [shards[month] for month in sorted(source_rows)]
    manifest = cloud_manifest(ordered, foreground, MODEL, MODEL_DIGEST, MODEL_REVISION)
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
) -> None:
    """Validate one aligned physical-dedupe month and its omission proof."""
    month = source_row["month"]
    if row.get("source_sha256") != source_row.get("sha256"):
        raise RuntimeError(f"Archive cloud source drifted: {month}")
    if not valid_asset(output / row["points"]["path"], row.get("points")):
        raise RuntimeError(f"Archive cloud points drifted: {month}")
    if not valid_asset(output / row["meta"]["path"], row.get("meta")):
        raise RuntimeError(f"Archive cloud metadata drifted: {month}")
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
    if (
        meta.get("count") != row["count"]
        or len(kept_ids) != row["count"]
        or len(set(kept_ids) | set(omitted_ids)) != row["source_count"]
        or set(kept_ids).intersection(omitted_ids)
    ):
        raise RuntimeError(f"Archive cloud metadata coverage drifted: {month}")
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
) -> dict:
    """Require exact source coverage and self-verifying browser assets."""
    source = read_manifest(archive)
    foreground = foreground or {}
    cloud = read_cloud(output / "index.json")
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
            archive, output, source_rows[month], row, foreground.get(month, set())
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
            args.archive, args.output, load_foreground(args.atlas)
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
        )
        print(f"Published {manifest['count']:,} historical semantic points")


if __name__ == "__main__":
    main()
