"""Build deterministic semantic regions from atlas embeddings."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, silhouette_score

Record = tuple[str, str] | Mapping[str, Any]
METHOD = "embedding-normalized-kmeans-v1"
MIN_SIZE = 15
MAX_SHARE = 0.35
KIND = "coarse embedding neighborhoods"
MIN_LABEL_SCORE = 0.3
MIN_SILHOUETTE = 0.0
MIN_STABILITY = 0.2
BLOCKED_LABELS = frozenset(
    {"adam", "collection", "differential", "does", "neural", "systems"}
)
TAXON = re.compile(
    r"^(?:machine learning research area|machine learning method):\s*([^.]*)",
    re.IGNORECASE,
)
SPACE = re.compile(r"\s+")
STOPS = frozenset(ENGLISH_STOP_WORDS) | {
    "adam",
    "areas",
    "approach",
    "area",
    "collection",
    "completed",
    "currently",
    "data",
    "differential",
    "does",
    "field",
    "learning",
    "machine",
    "method",
    "methods",
    "network",
    "networks",
    "neural",
    "paper",
    "representative",
    "research",
    "study",
    "systems",
    "work",
}


def _parts(record: Record) -> tuple[str, str]:
    if isinstance(record, Mapping):
        node_id = str(record.get("id", ""))
        text = str(
            record.get("text") or record.get("title") or record.get("label") or ""
        )
        return node_id, text
    if len(record) != 2:
        raise ValueError("Each cluster record must contain an ID and text")
    return str(record[0]), str(record[1])


def _inputs(
    records: Sequence[Record], vectors: np.ndarray, points: np.ndarray
) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    parts = [_parts(record) for record in records]
    ids = [node_id for node_id, _ in parts]
    texts = [SPACE.sub(" ", text).strip() for _, text in parts]
    vector_data = np.asarray(vectors, dtype=np.float32)
    point_data = np.asarray(points, dtype=np.float32)
    if not ids:
        if vector_data.size or point_data.size:
            raise ValueError("Empty records require empty vectors and points")
        return ids, texts, vector_data.reshape(0, 0), point_data.reshape(0, 3)
    if any(not node_id for node_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Cluster record IDs must be non-empty and unique")
    if vector_data.ndim != 2 or vector_data.shape[0] != len(ids):
        raise ValueError("Embedding rows must align with cluster records")
    if point_data.shape != (len(ids), 3):
        raise ValueError("3D points must align with cluster records")
    if not np.isfinite(vector_data).all() or not np.isfinite(point_data).all():
        raise ValueError("Cluster inputs must contain only finite values")
    norms = np.linalg.norm(vector_data, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Embedding vectors must be non-zero")
    return ids, texts, vector_data / norms, point_data


def _total(size: int) -> int:
    if size < 8:
        return 1
    return min(32, max(2, round(np.sqrt(size) / 2)))


def _model(cluster_count: int, seed: int) -> KMeans:
    return KMeans(
        n_clusters=cluster_count,
        random_state=seed,
        n_init=1,
        max_iter=300,
        algorithm="lloyd",
    )


def _groups(
    vectors: np.ndarray, texts: Sequence[str], cluster_count: int
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    fit_indexes = np.asarray(
        [
            index
            for index, text in enumerate(texts)
            if not _taxon(text) and not _context(text)
        ],
        dtype=np.int32,
    )
    if len(fit_indexes) < cluster_count:
        fit_indexes = np.arange(len(vectors), dtype=np.int32)
    if cluster_count == 1:
        labels = np.zeros(len(vectors), dtype=np.int32)
        center = vectors[fit_indexes].mean(axis=0, keepdims=True)
        return labels, 0.0, center, fit_indexes
    model = _model(cluster_count, 42).fit(vectors[fit_indexes])
    labels = model.predict(vectors)
    return labels, float(model.inertia_), model.cluster_centers_, fit_indexes


def _balance(labels: np.ndarray, cluster_count: int) -> tuple[int, float]:
    counts = np.bincount(labels, minlength=cluster_count)
    minimum = int(counts.min())
    max_share = float(counts.max() / len(labels))
    min_gate = min(MIN_SIZE, max(1, len(labels) // (cluster_count * 3)))
    share_gate = max(MAX_SHARE, min(1.0, 1.5 / cluster_count))
    if minimum < min_gate or max_share > share_gate:
        raise RuntimeError(
            f"Unbalanced semantic regions: min={minimum}, max_share={max_share:.3f}"
        )
    return minimum, max_share


def _quality(
    vectors: np.ndarray,
    labels: np.ndarray,
    fit_indexes: np.ndarray,
    cluster_count: int,
    inertia: float,
) -> dict[str, Any]:
    fit_vectors = vectors[fit_indexes]
    fit_labels = labels[fit_indexes]
    if cluster_count == 1:
        silhouette = 0.0
        stability = 1.0
    else:
        silhouette = silhouette_score(
            fit_vectors,
            fit_labels,
            metric="cosine",
        )
        other = _model(cluster_count, 43).fit(fit_vectors)
        stability = adjusted_rand_score(fit_labels, other.predict(fit_vectors))
    if (
        not math.isfinite(silhouette)
        or not math.isfinite(stability)
        or silhouette < MIN_SILHOUETTE
        or stability < MIN_STABILITY
    ):
        raise RuntimeError(
            "Coarse embedding neighborhoods fail their quality thresholds"
        )
    return {
        "inertia": round(inertia, 6),
        "mean_inertia": round(inertia / len(fit_indexes), 6),
        "silhouette": round(float(silhouette), 6),
        "stability_ari": round(float(stability), 6),
        "fit_count": int(len(fit_indexes)),
        "silhouette_count": int(len(fit_indexes)),
        "thresholds": {
            "silhouette": MIN_SILHOUETTE,
            "stability_ari": MIN_STABILITY,
        },
    }


def _taxon(text: str) -> str:
    match = TAXON.match(text)
    return SPACE.sub(" ", match.group(1)).strip().lower() if match else ""


def _context(text: str) -> bool:
    return text.casefold().startswith("collection entry:")


def _features(texts: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    corpus = ["" if _taxon(text) or _context(text) else text for text in texts]
    if not any(corpus):
        return np.empty((len(texts), 0)), np.asarray([], dtype=str)
    vectorizer = TfidfVectorizer(
        lowercase=True,
        max_features=6_000,
        ngram_range=(1, 2),
        stop_words=sorted(STOPS),
        sublinear_tf=True,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9-]{2,}\b",
    )
    try:
        matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        return np.empty((len(texts), 0)), np.asarray([], dtype=str)
    return matrix, vectorizer.get_feature_names_out()


def _medoid(
    indexes: np.ndarray, ids: Sequence[str], vectors: np.ndarray
) -> tuple[int, np.ndarray]:
    members = vectors[indexes]
    scores = members @ members.sum(axis=0)
    ranked = sorted(
        zip(scores.tolist(), indexes.tolist(), strict=True),
        key=lambda item: (-round(item[0], 12), ids[item[1]]),
    )
    medoid_index = ranked[0][1]
    distances = np.clip(1 - members @ vectors[medoid_index], 0, 2)
    return medoid_index, distances


def _add(terms: list[str], candidate: str) -> None:
    value = SPACE.sub(" ", candidate).strip(" .:-").lower()
    if not value or value in terms:
        return
    words = set(value.replace("-", " ").split())
    existing = [set(term.replace("-", " ").split()) for term in terms]
    if any(words <= term_words for term_words in existing):
        return
    terms.append(value)


def _terms(
    indexes: np.ndarray,
    matrix: np.ndarray,
    features: np.ndarray,
    marker: str,
) -> list[str]:
    terms: list[str] = []
    _add(terms, marker)
    if len(features):
        scores = np.asarray(matrix[indexes].mean(axis=0)).ravel()
        ranked = sorted(
            range(len(features)),
            key=lambda index: (
                -round(float(scores[index]), 12),
                -str(features[index]).count(" "),
                str(features[index]),
            ),
        )
        for index in ranked:
            if scores[index] <= 0:
                break
            _add(terms, str(features[index]))
            if len(terms) == 5:
                break
    return (terms or ["semantic region"])[:5]


def _markers(
    texts: Sequence[str], vectors: np.ndarray, centers: np.ndarray
) -> dict[int, tuple[str, float]]:
    taxon_indexes = [index for index, text in enumerate(texts) if _taxon(text)]
    if len(taxon_indexes) < len(centers):
        raise RuntimeError("Semantic regions require one taxonomy marker per center")
    center_norms = np.linalg.norm(centers, axis=1, keepdims=True)
    center_data = centers / np.maximum(center_norms, np.finfo(np.float32).eps)
    similarities = center_data @ vectors[taxon_indexes].T
    center_rows, taxon_cols = linear_sum_assignment(-similarities)
    markers = {
        int(center): (
            _taxon(texts[taxon_indexes[int(taxon)]]),
            float(similarities[int(center), int(taxon)]),
        )
        for center, taxon in zip(center_rows, taxon_cols, strict=True)
    }
    if any(
        label in BLOCKED_LABELS or score < MIN_LABEL_SCORE
        for label, score in markers.values()
    ):
        raise RuntimeError("Semantic region labels are weak or generic")
    return markers


def _cluster_id(medoid: str) -> str:
    digest = hashlib.sha256(medoid.encode("utf-8")).hexdigest()[:10]
    return f"cluster-{digest}"


def _round(values: np.ndarray, digits: int = 3) -> list[float]:
    return [round(float(value), digits) for value in values]


def _row(
    indexes: np.ndarray,
    ids: Sequence[str],
    texts: Sequence[str],
    vectors: np.ndarray,
    points: np.ndarray,
    matrix: np.ndarray,
    features: np.ndarray,
    marker: tuple[str, float],
) -> dict[str, Any]:
    medoid_index, semantic_distances = _medoid(indexes, ids, vectors)
    centroid = points[indexes].mean(axis=0)
    point_distances = np.linalg.norm(points[indexes] - centroid, axis=1)
    label, label_score = marker
    terms = _terms(indexes, matrix, features, label)
    return {
        "id": _cluster_id(ids[medoid_index]),
        "label": terms[0],
        "label_source": "one-to-one taxonomy match",
        "label_similarity": round(label_score, 5),
        "centroid": _round(centroid),
        "count": int(len(indexes)),
        "radius": round(float(np.percentile(point_distances, 90)), 3),
        "medoid": ids[medoid_index],
        "spread": round(float(np.percentile(semantic_distances, 90)), 4),
        "terms": terms,
        "indexes": indexes,
    }


def build_clusters(
    records: Sequence[Record],
    vectors: np.ndarray,
    points: np.ndarray,
    *,
    cluster_count: int | None = None,
) -> dict[str, Any]:
    """Return layout-ready semantic regions and per-node assignments."""
    ids, texts, vector_data, point_data = _inputs(records, vectors, points)
    if not ids:
        return {
            "cluster_method": METHOD,
            "cluster_kind": KIND,
            "cluster_quality": {
                "inertia": 0.0,
                "mean_inertia": 0.0,
                "silhouette": 0.0,
                "stability_ari": 1.0,
                "fit_count": 0,
                "silhouette_count": 0,
                "thresholds": {
                    "silhouette": MIN_SILHOUETTE,
                    "stability_ari": MIN_STABILITY,
                },
                "min_count": 0,
                "max_share": 0.0,
            },
            "clusters": [],
            "node_clusters": {},
        }
    total = _total(len(ids)) if cluster_count is None else cluster_count
    if not isinstance(total, int) or not 1 <= total <= len(ids):
        raise ValueError("Cluster count must be between one and the node count")
    labels, inertia, centers, fit_indexes = _groups(vector_data, texts, total)
    min_count, max_share = _balance(labels, total)
    matrix, features = _features(texts)
    markers = (
        _markers(texts, vector_data, centers) if total > 1 else {0: ("atlas", 1.0)}
    )
    rows = [
        _row(
            np.flatnonzero(labels == label),
            ids,
            texts,
            vector_data,
            point_data,
            matrix,
            features,
            markers[label],
        )
        for label in range(total)
    ]
    rows.sort(key=lambda row: (row["label"], row["medoid"]))
    assignments = {
        ids[int(index)]: row["id"] for row in rows for index in row.pop("indexes")
    }
    quality = _quality(vector_data, labels, fit_indexes, total, inertia)
    quality.update({"min_count": min_count, "max_share": round(max_share, 6)})
    return {
        "cluster_method": METHOD,
        "cluster_kind": KIND,
        "cluster_quality": quality,
        "clusters": rows,
        "node_clusters": assignments,
    }
