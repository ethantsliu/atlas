#!/usr/bin/env python3
"""Audit scientific layout artifacts from the local embedding cache."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from cluster import build_clusters
from embed import (
    CACHE_PATH,
    alias_exclusions,
    cohort_ids,
    load_details,
    node_records,
    vector_hash,
    vector_sha,
)
from rules import check
from semantic import NEIGHBOR_COUNT, quality_report, semantic_neighbors


ROOT = Path(__file__).resolve().parents[1]
ATLAS_PATH = ROOT / "data/generated/atlas.json"
LAYOUT_PATH = ROOT / "data/generated/layout.json"
CACHE_FIELDS = {
    "digest",
    "model",
    "model_digest",
    "dimensions",
    "reducer",
    "vector_sha256",
    "vectors",
}
CLUSTER_FIELDS = (
    "cluster_method",
    "cluster_kind",
    "cluster_quality",
    "clusters",
    "node_clusters",
)
SCORE_QUANTUM = 0.000001


def cache_scalar(cache: Any, field: str) -> object:
    """Read one scalar cache value without accepting an array-shaped substitute."""
    value = cache[field]
    check(value.shape == (), f"Vector cache {field} is not scalar")
    return value.item()


def load_cache(path: Path) -> tuple[dict[str, object], np.ndarray]:
    """Load and structurally check the local cache without changing it."""
    with np.load(path, allow_pickle=False) as cache:
        check(CACHE_FIELDS <= set(cache.files), "Vector cache fields are incomplete")
        metadata = {
            field: cache_scalar(cache, field) for field in CACHE_FIELDS - {"vectors"}
        }
        vectors = cache["vectors"]
    return metadata, vectors


def audit_vectors(
    records: list[tuple[str, str]],
    layout: dict,
    path: Path,
) -> np.ndarray:
    """Verify cache alignment, metadata, and canonical vector bytes."""
    metadata, vectors = load_cache(path)
    embedding = layout.get("embedding", {})
    expected_input = vector_hash(records)
    checks = (
        (metadata["digest"] == expected_input, "Vector cache input is stale"),
        (
            embedding.get("input_sha256") == expected_input,
            "Layout vector input is stale",
        ),
        (metadata["model"] == embedding.get("model"), "Vector cache model is stale"),
        (
            metadata["model_digest"] == embedding.get("artifact_sha256"),
            "Vector cache model artifact is stale",
        ),
        (
            metadata["dimensions"] == embedding.get("dimensions"),
            "Vector cache dimensions are stale",
        ),
        (
            metadata["reducer"] == json.dumps(layout.get("reducer"), sort_keys=True),
            "Vector cache reducer is stale",
        ),
    )
    for condition, message in checks:
        check(condition, message)
    check(
        vectors.dtype == np.float32
        and vectors.shape == (len(records), embedding.get("dimensions"))
        and np.isfinite(vectors).all()
        and np.all(np.linalg.norm(vectors, axis=1) > 0),
        "Vector cache matrix is invalid",
    )
    actual_sha = vector_sha(vectors)
    check(metadata["vector_sha256"] == actual_sha, "Vector cache SHA is invalid")
    check(
        embedding.get("vector_sha256") == actual_sha,
        "Layout vector SHA disagrees with the cache",
    )
    return vectors


def neighbors_match(published: object, expected: dict[str, list[dict]]) -> bool:
    """Compare exact ranks while allowing one serialized float-score quantum."""
    if not isinstance(published, dict) or set(published) != set(expected):
        return False
    for node_id, expected_rows in expected.items():
        rows = published.get(node_id)
        if not isinstance(rows, list) or len(rows) != len(expected_rows):
            return False
        for row, expected_row in zip(rows, expected_rows, strict=True):
            score = row.get("score") if isinstance(row, dict) else None
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or row.get("id") != expected_row["id"]
                or not math.isclose(
                    score,
                    expected_row["score"],
                    rel_tol=0,
                    abs_tol=SCORE_QUANTUM + 1e-12,
                )
            ):
                return False
    return True


def audit_layout(
    atlas: dict,
    details: dict[str, dict],
    cache_path: Path = CACHE_PATH,
    layout: dict | None = None,
) -> None:
    """Recompute every vector-derived public field and require exact output."""
    published = atlas.get("layout") if layout is None else layout
    check(isinstance(published, dict), "Scientific layout is missing")
    records = node_records(atlas, details)
    vectors = audit_vectors(records, published, cache_path)
    positions = published.get("positions", {})
    node_ids = [node_id for node_id, _ in records]
    check(
        isinstance(positions, dict) and set(positions) == set(node_ids),
        "Layout positions do not align with cache",
    )
    points = np.asarray([positions[node_id] for node_id in node_ids], dtype=np.float32)
    check(
        points.shape == (len(records), 3) and np.isfinite(points).all(),
        "Layout positions are invalid",
    )
    exclusions = alias_exclusions(atlas, records)
    expected_neighbors = semantic_neighbors(
        records,
        vectors,
        count=NEIGHBOR_COUNT,
        exclusions=exclusions,
    )
    check(
        published.get("neighbor_count") == NEIGHBOR_COUNT
        and neighbors_match(published.get("neighbors"), expected_neighbors),
        "Layout exact neighbors disagree with cached vectors",
    )
    expected_quality = quality_report(
        records,
        vectors,
        points,
        cohort_ids(atlas, records),
        exclusions=exclusions,
    )
    check(
        published.get("quality") == expected_quality,
        "Layout quality or cohort metrics disagree with cached vectors",
    )
    expected_clusters = build_clusters(records, vectors, points)
    check(
        all(
            published.get(field) == expected_clusters[field] for field in CLUSTER_FIELDS
        ),
        "Layout clusters disagree with cached vectors",
    )


def main() -> None:
    atlas = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    audit_layout(atlas, load_details(), layout=layout)
    print(f"Audited {layout['node_count']:,} semantic-layout nodes")


if __name__ == "__main__":
    main()
