"""Measure and publish semantic-layout fidelity without publishing vectors."""

from __future__ import annotations

import math

import numpy as np


QUALITY_K = 10
NEIGHBOR_COUNT = 8
MIN_TRUST = 0.9
MIN_RECALL = 0.25
COHORT_GATES = {
    "all": {"trustworthiness": 0.9, "knn_recall": 0.25},
    "paper": {"trustworthiness": 0.9, "knn_recall": 0.25},
    "idea": {"trustworthiness": 0.95, "knn_recall": 0.4},
    "taxonomy": {"trustworthiness": 0.88, "knn_recall": 0.33},
    "context": {"trustworthiness": 0.0, "knn_recall": 0.0},
}


def unit_rows(values: np.ndarray) -> np.ndarray:
    """Return canonical float64 unit rows with safe zero-vector handling."""
    matrix = np.asarray(values, dtype=np.float64)
    norms = np.sqrt(np.sum(matrix * matrix, axis=1, keepdims=True, dtype=np.float64))
    return matrix / np.maximum(norms, np.finfo(np.float64).eps)


def cosine_top(
    vectors: np.ndarray,
    count: int,
    blocked: list[set[int]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Find deterministic exact cosine neighbors, excluding each row itself."""
    if not 0 < count < len(vectors):
        raise ValueError("Neighbor count must be between zero and the row count")
    normalized = unit_rows(vectors)
    scores = normalized @ normalized.T
    np.fill_diagonal(scores, -np.inf)
    if blocked is not None:
        if len(blocked) != len(vectors):
            raise ValueError("Blocked-neighbor rows must align with vectors")
        for row, indexes in enumerate(blocked):
            if indexes:
                scores[row, list(indexes)] = -np.inf
    indexes = np.argsort(-scores, axis=1, kind="stable")[:, :count]
    top_scores = np.take_along_axis(scores, indexes, axis=1)
    if not np.isfinite(top_scores).all():
        raise ValueError("Too few non-alias neighbors remain")
    return indexes, top_scores


def point_top(
    points: np.ndarray,
    count: int,
    blocked: list[set[int]] | None = None,
) -> np.ndarray:
    """Find deterministic Euclidean neighbors in the rendered projection."""
    values = np.asarray(points, dtype=np.float32)
    deltas = values[:, None, :] - values[None, :, :]
    distances = np.einsum("ijk,ijk->ij", deltas, deltas)
    np.fill_diagonal(distances, np.inf)
    if blocked is not None:
        for row, indexes in enumerate(blocked):
            if indexes:
                distances[row, list(indexes)] = np.inf
    return np.argsort(distances, axis=1, kind="stable")[:, :count]


def blocked_rows(
    records: list[tuple[str, str]],
    exclusions: dict[str, set[str]] | None,
) -> list[set[int]]:
    """Translate semantic alias IDs into aligned row indexes."""
    node_ids = [node_id for node_id, _ in records]
    id_indexes = {node_id: index for index, node_id in enumerate(node_ids)}
    return [
        {
            id_indexes[other_id]
            for other_id in (exclusions or {}).get(node_id, set())
            if other_id in id_indexes
        }
        for node_id in node_ids
    ]


def recall_at(
    vectors: np.ndarray,
    points: np.ndarray,
    count: int = QUALITY_K,
) -> float:
    """Measure mean exact-neighbor recall from embedding space into 3D."""
    source, _ = cosine_top(vectors, count)
    projected = point_top(points, count)
    overlaps = [
        np.intersect1d(left, right, assume_unique=True).size
        for left, right in zip(source, projected, strict=True)
    ]
    return float(np.mean(overlaps) / count)


def quality_rows(
    vectors: np.ndarray,
    points: np.ndarray,
    count: int = QUALITY_K,
    blocked: list[set[int]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return standard trustworthiness and recall for every global-space row."""
    if not 0 < count < len(vectors) / 2:
        raise ValueError("Quality k must be below half the node count")
    normalized = unit_rows(vectors)
    scores = normalized @ normalized.T
    np.fill_diagonal(scores, -np.inf)
    blocked = blocked or [set() for _ in vectors]
    if len(blocked) != len(vectors):
        raise ValueError("Blocked-neighbor rows must align with vectors")
    for row, indexes in enumerate(blocked):
        if indexes:
            scores[row, list(indexes)] = -np.inf
    source_order = np.argsort(-scores, axis=1, kind="stable")
    source_top = source_order[:, :count]
    source_scores = np.take_along_axis(scores, source_top, axis=1)
    if not np.isfinite(source_scores).all():
        raise ValueError("Too few non-alias neighbors remain")
    ranks = np.empty(source_order.shape, dtype=np.int32)
    rows = np.arange(len(vectors))[:, None]
    ranks[rows, source_order] = np.arange(1, len(vectors) + 1)
    projected = point_top(points, count, blocked)
    trust_scores: list[float] = []
    recall_scores: list[float] = []
    for row, (source, visible) in enumerate(zip(source_top, projected, strict=True)):
        source_ids = set(source.tolist())
        intrusions = [index for index in visible if index not in source_ids]
        penalty = sum(int(ranks[row, index]) - count for index in intrusions)
        usable_count = len(vectors) - len(blocked[row])
        scale = count * (2 * usable_count - 3 * count - 1)
        trust_scores.append(1 - (2 * penalty / scale))
        recall_scores.append(len(source_ids & set(visible.tolist())) / count)
    return np.asarray(trust_scores), np.asarray(recall_scores)


def measure_quality(
    vectors: np.ndarray,
    points: np.ndarray,
    count: int = QUALITY_K,
) -> dict:
    """Measure local projection intrusions and exact-neighbor preservation."""
    trust, recall = quality_rows(vectors, points, count)
    return {
        "k": count,
        "trustworthiness": round(float(np.mean(trust)), 6),
        "knn_recall": round(float(np.mean(recall)), 6),
        "thresholds": {
            "trustworthiness": MIN_TRUST,
            "knn_recall": MIN_RECALL,
        },
    }


def measure_cohorts(
    records: list[tuple[str, str]],
    vectors: np.ndarray,
    points: np.ndarray,
    cohorts: dict[str, set[str]],
    count: int = QUALITY_K,
) -> dict[str, dict]:
    """Average global-neighborhood fidelity over named node cohorts."""
    node_ids = [node_id for node_id, _ in records]
    trust, recall = quality_rows(vectors, points, count)
    results: dict[str, dict] = {}
    for name, cohort_ids in cohorts.items():
        indexes = [
            index for index, node_id in enumerate(node_ids) if node_id in cohort_ids
        ]
        if not indexes:
            raise ValueError(f"Cohort {name} is empty")
        results[name] = {
            "node_count": len(indexes),
            "trustworthiness": round(float(np.mean(trust[indexes])), 6),
            "knn_recall": round(float(np.mean(recall[indexes])), 6),
        }
    return results


def quality_report(
    records: list[tuple[str, str]],
    vectors: np.ndarray,
    points: np.ndarray,
    cohorts: dict[str, set[str]],
    count: int = QUALITY_K,
    exclusions: dict[str, set[str]] | None = None,
) -> dict:
    """Build one global metric report and its per-kind row averages."""
    node_ids = [node_id for node_id, _ in records]
    trust, recall = quality_rows(
        vectors,
        points,
        count,
        blocked_rows(records, exclusions),
    )
    report = {
        "k": count,
        "trustworthiness": round(float(np.mean(trust)), 6),
        "knn_recall": round(float(np.mean(recall)), 6),
        "thresholds": {
            "trustworthiness": MIN_TRUST,
            "knn_recall": MIN_RECALL,
        },
        "alias_policy": "exclude canonical and identical-text aliases",
        "cohort_policy": "only present cohorts reported; research cohorts gated",
        "cohorts": {},
    }
    for name, cohort_ids in cohorts.items():
        indexes = [
            index for index, node_id in enumerate(node_ids) if node_id in cohort_ids
        ]
        if not indexes:
            raise ValueError(f"Cohort {name} is empty")
        report["cohorts"][name] = {
            "node_count": len(indexes),
            "trustworthiness": round(float(np.mean(trust[indexes])), 6),
            "knn_recall": round(float(np.mean(recall[indexes])), 6),
            "thresholds": COHORT_GATES.get(
                name,
                {"trustworthiness": 0.0, "knn_recall": 0.0},
            ),
        }
    return report


def ensure_quality(quality: dict) -> None:
    """Fail layout generation when measured fidelity misses either gate."""
    thresholds = quality["thresholds"]
    for metric in ("trustworthiness", "knn_recall"):
        if not math.isfinite(quality[metric]) or quality[metric] < thresholds[metric]:
            raise RuntimeError(
                f"Semantic layout {metric} {quality[metric]:.3f} is below "
                f"{thresholds[metric]:.3f}"
            )
    for name, cohort in quality.get("cohorts", {}).items():
        for metric, minimum in cohort["thresholds"].items():
            if not math.isfinite(cohort[metric]) or cohort[metric] < minimum:
                raise RuntimeError(
                    f"Semantic {name} {metric} {cohort[metric]:.3f} is below "
                    f"{minimum:.3f}"
                )


def semantic_neighbors(
    records: list[tuple[str, str]],
    vectors: np.ndarray,
    count: int = NEIGHBOR_COUNT,
    exclusions: dict[str, set[str]] | None = None,
) -> dict[str, list[dict]]:
    """Serialize exact original-space neighbors and rounded cosine scores."""
    node_ids = [node_id for node_id, _ in records]
    blocked = blocked_rows(records, exclusions)
    indexes, scores = cosine_top(vectors, count, blocked)
    return {
        node_id: [
            {"id": node_ids[int(index)], "score": round(float(score), 6)}
            for index, score in zip(row_indexes, row_scores, strict=True)
        ]
        for node_id, row_indexes, row_scores in zip(
            node_ids,
            indexes,
            scores,
            strict=True,
        )
    }
