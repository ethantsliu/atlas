"""Place unfitted ideas without changing the audited semantic projection."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter


METHOD = "support-centroid-80-20-3d-v1"


def _hash(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(body).hexdigest()


def base_hash(layout: dict) -> str:
    """Bind placements to the exact immutable coordinates they extend."""
    return _hash(
        {
            "method": layout.get("method"),
            "positions": layout.get("positions"),
            "node_clusters": layout.get("node_clusters"),
        }
    )


def idea_hash(ideas: list[dict]) -> str:
    """Hash only fields that determine derived idea placement."""
    rows = [
        {
            "id": idea["id"],
            "paper_ids": idea.get("brief", {}).get("paper_ids", []),
            "topic_ids": idea.get("topic_ids", []),
            "trick_ids": idea.get("trick_ids", []),
        }
        for idea in sorted(ideas, key=lambda row: row["id"])
    ]
    return _hash(rows)


def paper_map(atlas: dict) -> dict[str, str]:
    """Resolve both public graph IDs and stable paper IDs to graph nodes."""
    resolved: dict[str, str] = {}
    for paper in atlas["papers"]:
        resolved[paper["id"]] = paper["id"]
        stable_id = paper.get("stable_id")
        if stable_id:
            resolved[stable_id] = paper["id"]
    return resolved


def anchor_ids(idea: dict, resolved: dict[str, str], positions: dict) -> list[str]:
    """Return ordered, de-duplicated support and route anchors."""
    candidates = [
        *(resolved.get(value, "") for value in idea["brief"].get("paper_ids", [])),
        *(f"topic:{value}" for value in idea.get("topic_ids", [])),
        *(f"trick:{value}" for value in idea.get("trick_ids", [])),
    ]
    anchors: list[str] = []
    for node_id in candidates:
        if node_id and node_id in positions and node_id not in anchors:
            anchors.append(node_id)
    return anchors


def jitter(node_id: str, scale: float) -> list[float]:
    """Create a stable small 3D offset from an idea identity."""
    digest = hashlib.sha256(node_id.encode()).digest()
    values = [
        int.from_bytes(digest[index : index + 2], "big") - 32768 for index in (0, 2, 4)
    ]
    norm = math.sqrt(sum(value * value for value in values)) or 1
    return [scale * value / norm for value in values]


def idea_point(
    anchors: list[str], positions: dict, node_id: str, scale: float = 2
) -> list[float]:
    """Interpolate paper and taxonomy evidence, then avoid exact overlap."""
    papers = [
        positions[value]
        for value in anchors
        if not value.startswith(("topic:", "trick:"))
    ]
    routes = [
        positions[value] for value in anchors if value.startswith(("topic:", "trick:"))
    ]

    def center(points: list[list[float]]) -> list[float]:
        return [sum(point[axis] for point in points) / len(points) for axis in range(3)]

    if papers and routes:
        paper_center = center(papers)
        route_center = center(routes)
        point = [
            0.8 * paper_center[axis] + 0.2 * route_center[axis] for axis in range(3)
        ]
    else:
        point = center(papers or routes)
    offset = jitter(node_id, scale)
    return [round(point[axis] + offset[axis], 3) for axis in range(3)]


def idea_cluster(anchors: list[str], assignments: dict[str, str]) -> str:
    """Inherit the modal fitted cluster from an idea's evidence anchors."""
    counts = Counter(assignments[value] for value in anchors if value in assignments)
    if not counts:
        raise ValueError("Derived idea has no fitted cluster anchor")
    return min(counts, key=lambda value: (-counts[value], value))


def build_places(atlas: dict, layout: dict) -> dict:
    """Build a deterministic visual overlay for ideas absent from UMAP."""
    positions = layout.get("positions", {})
    assignments = layout.get("node_clusters", {})
    resolved = paper_map(atlas)
    ideas = sorted(
        (idea for idea in atlas["ideas"] if idea["id"] not in positions),
        key=lambda row: row["id"],
    )
    placed: dict[str, list[float]] = {}
    neighbors: dict[str, list[str]] = {}
    clusters: dict[str, str] = {}
    occupied = {tuple(point) for point in positions.values()}
    for idea in ideas:
        anchors = anchor_ids(idea, resolved, positions)
        if not anchors:
            raise ValueError(f"Derived idea has no fitted anchors: {idea['id']}")
        point = idea_point(anchors, positions, idea["id"])
        for attempt in range(1, 17):
            if tuple(point) not in occupied:
                break
            point = idea_point(anchors, positions, idea["id"], 2 + attempt)
        if tuple(point) in occupied:
            raise ValueError(f"Derived idea coordinate collision: {idea['id']}")
        occupied.add(tuple(point))
        placed[idea["id"]] = point
        neighbors[idea["id"]] = anchors[:8]
        clusters[idea["id"]] = idea_cluster(anchors, assignments)
    return {
        "schema_version": 1,
        "method": METHOD,
        "base_method": layout.get("method"),
        "base_node_count": layout.get("node_count"),
        "base_sha256": base_hash(layout),
        "input_sha256": idea_hash(ideas),
        "node_count": len(ideas),
        "positions": placed,
        "neighbors": neighbors,
        "node_clusters": clusters,
    }


def base_atlas(atlas: dict) -> dict:
    """Return the fitted semantic subset while preserving all other data."""
    overlay = atlas.get("idea_layout", {})
    derived = set(overlay.get("positions", {})) if isinstance(overlay, dict) else set()
    if not derived:
        return atlas
    return {
        **atlas,
        "ideas": [idea for idea in atlas["ideas"] if idea["id"] not in derived],
    }


def validate_places(atlas: dict) -> None:
    """Rebuild and compare the complete deterministic overlay contract."""
    overlay = atlas.get("idea_layout")
    layout = atlas.get("layout")
    if overlay is None:
        missing = [
            idea["id"]
            for idea in atlas["ideas"]
            if idea["id"] not in layout.get("positions", {})
        ]
        if missing:
            raise ValueError("Unfitted ideas require a derived placement overlay")
        return
    if not isinstance(overlay, dict) or set(overlay) != {
        "schema_version",
        "method",
        "base_method",
        "base_node_count",
        "base_sha256",
        "input_sha256",
        "node_count",
        "positions",
        "neighbors",
        "node_clusters",
    }:
        raise ValueError("Derived idea layout has an invalid shape")
    if overlay != build_places(atlas, layout):
        raise ValueError("Derived idea layout is stale")
