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
from node import clip_words


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
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--provider", choices=("native", "ollama"), default="native")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, int(os.getenv("ATLAS_EMBED_WORKERS", "1"))),
    )
    return parser.parse_args()


def archive_text(paper: dict) -> str:
    """Represent a paper with title, abstract, and categories—not title alone."""
    categories = ", ".join(paper.get("categories", []))
    return " ".join(
        part
        for part in (
            f"research paper: {clip_words(paper.get('title'), 160)}",
            f"abstract: {clip_words(paper.get('abstract'), 360)}",
            f"areas: {clip_words(categories, 80)}",
        )
        if part.split(": ", 1)[-1]
    )


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


def write_month(
    month: str,
    source_sha: str,
    papers: list[dict],
    vectors: np.ndarray,
    anchors: tuple[np.ndarray, np.ndarray],
    output: Path,
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
    return {
        "month": month,
        "source_sha256": source_sha,
        "count": len(papers),
        "counts": counts,
        "points": asset_meta(point_path),
        "meta": asset_meta(meta_path),
    }


def read_cloud(path: Path) -> dict:
    """Read the prior incremental point manifest when present."""
    if not path.exists():
        return {"schema_version": 1, "shards": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Archive point manifest is invalid") from error
    if value.get("schema_version") != 1 or not isinstance(value.get("shards"), list):
        raise RuntimeError("Archive point manifest has an invalid contract")
    return value


def build_cloud(
    archive: Path,
    anchor_path: Path,
    cache: Path,
    output: Path,
    batch_size: int,
    workers: int = 1,
    provider: str = "native",
) -> dict:
    """Incrementally build every locally available changed archive month."""
    source = read_manifest(archive)
    source_rows = {row["month"]: row for row in source["shards"]}
    prior = read_cloud(output / "index.json")
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
        if prior_row and prior_row.get("source_sha256") == source_sha:
            point_path = output / prior_row["points"]["path"]
            meta_path = output / prior_row["meta"]["path"]
            if point_path.exists() and meta_path.exists():
                continue
        payload = read_shard(path)
        papers = payload["papers"]
        records = [(paper["id"], archive_text(paper)) for paper in papers]
        vectors = embed_records(month, records, cache, batch_size, workers, provider)
        shards[month] = write_month(month, source_sha, papers, vectors, anchors, output)
    ordered = [shards[month] for month in sorted(shards)]
    manifest = {
        "schema_version": 1,
        "source": "arxiv",
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "model_revision": MODEL_REVISION,
        "projection": "anchor-cosine-8-v1",
        "point_bytes": 13,
        "count": sum(row["count"] for row in ordered),
        "counts": {
            scope: sum(row["counts"][scope] for row in ordered) for scope in SCOPES
        },
        "shards": ordered,
    }
    atomic_write_text(
        output / "index.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def main() -> None:
    """Build the historical semantic point cloud."""
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    manifest = build_cloud(
        args.archive,
        args.anchors,
        args.cache,
        args.output,
        args.batch_size,
        args.workers,
        args.provider,
    )
    print(f"Published {manifest['count']:,} historical semantic points")


if __name__ == "__main__":
    main()
