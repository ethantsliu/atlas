"""Validate semantic layout provenance, fidelity, neighbors, and regions."""

from __future__ import annotations

import math
import re

from cluster import BLOCKED_LABELS, KIND as CLUSTER_KIND
from cluster import (
    MAX_SHARE,
    METHOD as CLUSTER_METHOD,
    MIN_LABEL_SCORE,
    MIN_SILHOUETTE,
    MIN_SIZE,
    MIN_STABILITY,
)
from embed import input_hash, node_records, vector_hash
from layout import (
    EMBED_DIM,
    LAYOUT_METHOD,
    MODEL_CONTEXT,
    MODEL_DIGEST,
    MODEL_NAME,
    OLLAMA_VERSION,
    REDUCER,
)
from rules import check
from semantic import (
    COHORT_GATES,
    MIN_RECALL,
    MIN_TRUST,
    NEIGHBOR_COUNT,
    QUALITY_K,
)


def valid_score(value: object) -> bool:
    """Return whether a value is a finite normalized numeric score."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def validate_quality(layout: dict, cohort_sizes: dict[str, int]) -> None:
    """Require reproducible projection metrics to clear fixed quality gates."""
    quality = layout.get("quality", {})
    thresholds = quality.get("thresholds", {})
    check(
        quality.get("alias_policy") == "exclude canonical and identical-text aliases",
        "Layout quality alias policy is stale",
    )
    check(
        quality.get("cohort_policy")
        == "research cohorts gated; context reported descriptively",
        "Layout quality cohort policy is stale",
    )
    check(quality.get("k") == QUALITY_K, "Layout quality neighborhood is stale")
    check(
        thresholds == {"trustworthiness": MIN_TRUST, "knn_recall": MIN_RECALL},
        "Layout quality thresholds are stale",
    )
    for metric, minimum in (
        ("trustworthiness", MIN_TRUST),
        ("knn_recall", MIN_RECALL),
    ):
        score = quality.get(metric)
        check(
            valid_score(score) and score >= minimum,
            f"Layout {metric} misses its quality gate",
        )
    cohorts = quality.get("cohorts", {})
    check(set(cohorts) == set(cohort_sizes), "Layout quality cohorts are stale")
    for name, size in cohort_sizes.items():
        cohort = cohorts[name]
        check(cohort.get("node_count") == size, f"Layout {name} cohort is stale")
        check(
            cohort.get("thresholds") == COHORT_GATES[name],
            f"Layout {name} cohort thresholds are stale",
        )
        check(
            valid_score(cohort.get("trustworthiness"))
            and valid_score(cohort.get("knn_recall")),
            f"Layout {name} cohort metrics are invalid",
        )
        check(
            all(
                cohort[metric] >= minimum
                for metric, minimum in COHORT_GATES[name].items()
            ),
            f"Layout {name} cohort misses its quality gate",
        )
    check(
        cohorts["all"]["trustworthiness"] == quality["trustworthiness"]
        and cohorts["all"]["knn_recall"] == quality["knn_recall"],
        "Layout all-cohort metrics disagree",
    )


def validate_neighbors(layout: dict, graph_ids: set[str]) -> None:
    """Require exact original-space neighbors for every public graph node."""
    count = layout.get("neighbor_count")
    neighbors = layout.get("neighbors", {})
    check(count == NEIGHBOR_COUNT, "Semantic neighbor count is stale")
    check(set(neighbors) == graph_ids, "Semantic neighbors do not cover the graph")
    for node_id, entries in neighbors.items():
        check(len(entries) == count, f"Semantic neighbors are stale for {node_id}")
        ids = [entry.get("id") for entry in entries]
        scores = [entry.get("score") for entry in entries]
        check(
            len(set(ids)) == count and node_id not in ids and set(ids) <= graph_ids,
            f"Semantic neighbor ids are invalid for {node_id}",
        )
        check(
            all(
                isinstance(score, (int, float))
                and math.isfinite(score)
                and -1 <= score <= 1
                for score in scores
            )
            and scores == sorted(scores, reverse=True),
            f"Semantic neighbor scores are invalid for {node_id}",
        )


def validate_cluster(row: dict, graph_ids: set[str]) -> None:
    """Require one human-readable semantic region with valid geometry."""
    label = row.get("label")
    centroid = row.get("centroid")
    terms = row.get("terms")
    check(
        isinstance(label, str) and bool(label) and label == label.lower(),
        "Semantic cluster label is invalid",
    )
    check(
        row.get("label_source") == "one-to-one taxonomy match",
        "Semantic cluster label source is invalid",
    )
    label_score = row.get("label_similarity")
    check(
        isinstance(label_score, (int, float))
        and not isinstance(label_score, bool)
        and math.isfinite(label_score)
        and MIN_LABEL_SCORE <= label_score <= 1,
        "Semantic cluster label similarity is invalid",
    )
    check(
        isinstance(centroid, list)
        and len(centroid) == 3
        and all(
            isinstance(value, (int, float)) and math.isfinite(value)
            for value in centroid
        ),
        f"Semantic cluster centroid is invalid for {row.get('id')}",
    )
    check(
        isinstance(row.get("count"), int)
        and not isinstance(row["count"], bool)
        and row["count"] > 0,
        f"Semantic cluster count is invalid for {row.get('id')}",
    )
    for field, maximum in (("radius", None), ("spread", 2)):
        value = row.get(field)
        check(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
            and (maximum is None or value <= maximum),
            f"Semantic cluster {field} is invalid for {row.get('id')}",
        )
    check(row.get("medoid") in graph_ids, "Semantic cluster medoid is invalid")
    check(
        isinstance(terms, list)
        and bool(terms)
        and len(terms) <= 5
        and len(terms) == len(set(terms))
        and all(
            isinstance(term, str) and term and term == term.lower() for term in terms
        ),
        f"Semantic cluster terms are invalid for {row.get('id')}",
    )


def validate_clusters(layout: dict, graph_ids: set[str], fit_count: int) -> None:
    """Require balanced semantic regions and exact node assignments."""
    clusters = layout.get("clusters")
    assignments = layout.get("node_clusters")
    quality = layout.get("cluster_quality", {})
    check(layout.get("cluster_method") == CLUSTER_METHOD, "Unknown cluster method")
    check(layout.get("cluster_kind") == CLUSTER_KIND, "Unknown cluster kind")
    check(isinstance(clusters, list) and bool(clusters), "Clusters are missing")
    check(isinstance(assignments, dict), "Cluster assignments are missing")
    cluster_ids = [row.get("id") for row in clusters]
    check(
        all(isinstance(cluster_id, str) and cluster_id for cluster_id in cluster_ids)
        and len(cluster_ids) == len(set(cluster_ids)),
        "Semantic cluster ids are invalid",
    )
    labels = [row.get("label") for row in clusters]
    check(len(labels) == len(set(labels)), "Semantic cluster labels are not unique")
    check(
        not (
            ({"atlas", "semantic region", "research"} | set(BLOCKED_LABELS))
            & set(labels)
        ),
        "Semantic cluster label is generic",
    )
    check(set(assignments) == graph_ids, "Cluster assignments do not cover the graph")
    check(
        set(assignments.values()) == set(cluster_ids),
        "Cluster references are invalid",
    )
    for row in clusters:
        validate_cluster(row, graph_ids)
        assigned = sum(value == row["id"] for value in assignments.values())
        check(assigned == row["count"], f"Cluster count is stale for {row['id']}")
        check(assignments[row["medoid"]] == row["id"], "Cluster medoid is misassigned")
    counts = [row["count"] for row in clusters]
    check(sum(counts) == len(graph_ids), "Semantic cluster counts are stale")
    check(
        quality.get("min_count") == min(counts) >= MIN_SIZE,
        "Semantic cluster minimum is invalid",
    )
    check(
        quality.get("max_share") == round(max(counts) / len(graph_ids), 6)
        and quality["max_share"] <= MAX_SHARE,
        "Semantic cluster share is invalid",
    )
    for metric in ("inertia", "mean_inertia"):
        value = quality.get(metric)
        check(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0,
            f"Semantic cluster {metric} is invalid",
        )
    check(quality.get("fit_count") == fit_count, "Semantic cluster fit count is stale")
    check(
        quality.get("silhouette_count") == fit_count,
        "Semantic cluster silhouette count is stale",
    )
    cluster_thresholds = {
        "silhouette": MIN_SILHOUETTE,
        "stability_ari": MIN_STABILITY,
    }
    check(
        quality.get("thresholds") == cluster_thresholds,
        "Semantic cluster quality thresholds are stale",
    )
    for metric, minimum in cluster_thresholds.items():
        value = quality.get(metric)
        check(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and minimum <= value <= 1,
            f"Semantic cluster {metric} is invalid",
        )


def validate_layout(atlas: dict, details: dict[str, dict]) -> None:
    """Require measured semantic data for every public graph node."""
    layout = atlas.get("layout", {})
    embedding = layout.get("embedding", {})
    positions = layout.get("positions", {})
    graph_ids: set[str] = {
        *(f"topic:{item['id']}" for item in atlas["topics"]),
        *(f"trick:{item['id']}" for item in atlas["tricks"]),
        *(item["id"] for item in atlas["papers"]),
        *(item["id"] for item in atlas["ideas"]),
    }
    check(layout.get("schema_version") == 3, "Unknown layout schema version")
    check(layout.get("method") == LAYOUT_METHOD, "Unknown layout method")
    check(layout.get("model") == MODEL_NAME, "Unknown semantic embedding model")
    check(
        all(
            embedding.get(key) == value
            for key, value in {
                "provider": "ollama",
                "api": "embed-v1",
                "model": MODEL_NAME,
                "artifact_sha256": MODEL_DIGEST,
                "dimensions": EMBED_DIM,
                "context_length": MODEL_CONTEXT,
                "metric": "cosine",
                "runtime": f"ollama-{OLLAMA_VERSION}",
                "text_schema": "field-budget-v1",
                "truncate": False,
            }.items()
        ),
        "Semantic embedding configuration is stale",
    )
    check(
        all(
            isinstance(embedding.get(field), str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", embedding[field]))
            for field in ("input_sha256", "vector_sha256")
        ),
        "Semantic embedding hashes are invalid",
    )
    check(layout.get("reducer") == REDUCER, "Semantic reducer configuration is stale")
    records = node_records(atlas, details)
    check(
        embedding["input_sha256"] == vector_hash(records),
        "Semantic embedding input is stale",
    )
    check(
        layout.get("input_sha256") == input_hash(records, embedding["vector_sha256"]),
        "Semantic layout input is stale",
    )
    check(layout.get("node_count") == len(graph_ids), "Layout node count is stale")
    check(set(positions) == graph_ids, "Semantic coordinates do not cover the graph")
    check(
        all(
            isinstance(point, list)
            and len(point) == 3
            and all(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in point
            )
            for point in positions.values()
        ),
        "Semantic coordinates are invalid",
    )
    cohort_sizes = {
        "all": len(graph_ids),
        "paper": sum(
            item.get("record_kind") != "non_paper_context" for item in atlas["papers"]
        ),
        "context": sum(
            item.get("record_kind") == "non_paper_context" for item in atlas["papers"]
        ),
        "idea": len(atlas["ideas"]),
        "taxonomy": len(atlas["topics"]) + len(atlas["tricks"]),
    }
    validate_quality(layout, cohort_sizes)
    validate_neighbors(layout, graph_ids)
    validate_clusters(layout, graph_ids, cohort_sizes["paper"] + cohort_sizes["idea"])
