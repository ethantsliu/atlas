"""Measure cross-kind retrieval and positional mixing in the semantic layout."""

from __future__ import annotations

import numpy as np


NEIGHBOR_COUNT = 8
ROUTE_THRESHOLDS = {
    "semantic": {
        "topic": {"precision": 0.2, "hit_rate": 0.75},
        "trick": {"precision": 0.2, "hit_rate": 0.75},
        "combined": {"precision": 0.2, "hit_rate": 0.75},
    },
    "projected": {
        "topic": {"precision": 0.2, "hit_rate": 0.5},
        "trick": {"precision": 0.2, "hit_rate": 0.5},
        "combined": {"precision": 0.3, "hit_rate": 0.5},
    },
}
MAX_KIND_ETA = 0.05
MAX_DUPLICATES = 0


def route_sets(atlas: dict) -> dict[str, tuple[str, set[str]]]:
    """Map each taxonomy node to its routed research-paper IDs."""
    targets = {
        **{f"topic:{item['id']}": ("topic", set()) for item in atlas["topics"]},
        **{f"trick:{item['id']}": ("trick", set()) for item in atlas["tricks"]},
    }
    for paper in atlas["papers"]:
        if paper.get("record_kind") == "non_paper_context":
            continue
        for kind, field in (("topic", "topics"), ("trick", "tricks")):
            for route in paper.get(field, []):
                node_id = f"{kind}:{route.get('id')}"
                if node_id in targets:
                    targets[node_id][1].add(paper["id"])
    return targets


def route_metrics(atlas: dict, rankings: dict[str, list[str]]) -> dict:
    """Score routed-paper precision and hit rate by taxonomy kind."""
    totals = {
        "topic": {"correct": 0, "hits": 0, "count": 0},
        "trick": {"correct": 0, "hits": 0, "count": 0},
    }
    for node_id, (kind, relevant) in route_sets(atlas).items():
        found = sum(
            neighbor_id in relevant
            for neighbor_id in rankings[node_id][:NEIGHBOR_COUNT]
        )
        totals[kind]["correct"] += found
        totals[kind]["hits"] += bool(found)
        totals[kind]["count"] += 1
    totals["combined"] = {
        key: totals["topic"][key] + totals["trick"][key]
        for key in ("correct", "hits", "count")
    }
    return {
        kind: {
            "node_count": values["count"],
            "precision": round(
                values["correct"] / (values["count"] * NEIGHBOR_COUNT), 6
            )
            if values["count"]
            else 0.0,
            "hit_rate": round(values["hits"] / values["count"], 6)
            if values["count"]
            else 0.0,
        }
        for kind, values in totals.items()
    }


def point_rankings(
    positions: dict[str, list[float]], targets: set[str]
) -> dict[str, list[str]]:
    """Rank taxonomy targets by deterministic Euclidean distance in final 3D."""
    node_ids = sorted(positions)
    points = np.asarray([positions[node_id] for node_id in node_ids], dtype=np.float64)
    rankings: dict[str, list[str]] = {}
    for index, node_id in enumerate(node_ids):
        if node_id not in targets:
            continue
        distances = np.sum((points - points[index]) ** 2, axis=1)
        rankings[node_id] = [
            other_id
            for _, other_id in sorted(
                (
                    (round(float(distances[other]), 12), node_ids[other])
                    for other in range(len(node_ids))
                    if other != index
                )
            )[:NEIGHBOR_COUNT]
        ]
    return rankings


def kind_eta(atlas: dict, positions: dict[str, list[float]]) -> float:
    """Measure the share of positional variance explained by five node kinds."""
    contexts = {
        paper["id"]
        for paper in atlas["papers"]
        if paper.get("record_kind") == "non_paper_context"
    }
    ideas = {idea["id"] for idea in atlas["ideas"]}
    groups: dict[str, list[list[float]]] = {
        kind: [] for kind in ("topic", "trick", "paper", "idea", "context")
    }
    for node_id in sorted(positions):
        point = positions[node_id]
        if node_id.startswith("topic:"):
            kind = "topic"
        elif node_id.startswith("trick:"):
            kind = "trick"
        elif node_id in contexts:
            kind = "context"
        elif node_id in ideas:
            kind = "idea"
        else:
            kind = "paper"
        groups[kind].append(point)
    values = np.asarray([positions[node_id] for node_id in sorted(positions)])
    center = values.mean(axis=0)
    total = float(np.sum((values - center) ** 2))
    between = sum(
        len(points) * float(np.sum((np.asarray(points).mean(axis=0) - center) ** 2))
        for points in groups.values()
        if points
    )
    return round(between / total, 6) if total > 0 else 1.0


def duplicate_count(positions: dict[str, list[float]]) -> int:
    """Count nodes sharing an exact published coordinate triple."""
    points = [tuple(float(value) for value in point) for point in positions.values()]
    return len(points) - len(set(points))


def ensure_mix(report: dict) -> None:
    """Fail when retrieval or positional-mixing diagnostics miss fixed gates."""
    for space in ("semantic", "projected"):
        for kind in ("topic", "trick", "combined"):
            for metric, minimum in ROUTE_THRESHOLDS[space][kind].items():
                value = report[f"{space}_routes"][kind][metric]
                if value < minimum:
                    raise RuntimeError(
                        f"{space.title()} {kind} route {metric} "
                        f"{value:.3f} is below {minimum:.3f}"
                    )
    if report["position_eta_squared"] > MAX_KIND_ETA:
        raise RuntimeError("Node kind explains too much positional variance")
    if report["exact_coordinate_duplicates"] > MAX_DUPLICATES:
        raise RuntimeError("Semantic layout contains exact coordinate duplicates")


def mix_report(
    atlas: dict,
    neighbors: dict[str, list[dict]],
    positions: dict[str, list[float]],
) -> dict:
    """Build the complete public cross-kind layout diagnostic."""
    semantic = {
        node_id: [entry["id"] for entry in entries]
        for node_id, entries in neighbors.items()
    }
    targets = set(route_sets(atlas))
    report = {
        "kind": "cross-kind-layout-v1",
        "neighbor_count": NEIGHBOR_COUNT,
        "semantic_routes": route_metrics(atlas, semantic),
        "projected_routes": route_metrics(atlas, point_rankings(positions, targets)),
        "position_eta_squared": kind_eta(atlas, positions),
        "exact_coordinate_duplicates": duplicate_count(positions),
        "thresholds": {
            "routes": ROUTE_THRESHOLDS,
            "max_position_eta_squared": MAX_KIND_ETA,
            "max_exact_coordinate_duplicates": MAX_DUPLICATES,
        },
    }
    return report
