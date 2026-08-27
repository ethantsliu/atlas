"""Stabilize semantic coordinates against a prior public layout."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def load_prior(
    path: str | Path,
    allowed: set[str] | None = None,
) -> dict[str, list[float]]:
    """Load coordinates alone from a prior layout or canonical atlas."""
    try:
        text = (
            sys.stdin.read()
            if str(path) == "-"
            else Path(path).read_text(encoding="utf-8")
        )
        payload = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Prior semantic layout is unreadable") from error
    layout = payload.get("layout", payload) if isinstance(payload, dict) else None
    positions = layout.get("positions") if isinstance(layout, dict) else None
    if not isinstance(positions, dict):
        raise ValueError("Prior semantic layout lacks coordinates")
    result = {}
    for node_id, point in positions.items():
        if allowed is not None and node_id not in allowed:
            continue
        if (
            not isinstance(node_id, str)
            or not node_id
            or not isinstance(point, list)
            or len(point) != 3
            or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and np.isfinite(value)
                for value in point
            )
        ):
            raise ValueError("Prior semantic coordinates are invalid")
        result[node_id] = [float(value) for value in point]
    return result


def align_points(
    records: list[tuple[str, str]],
    points: np.ndarray,
    prior: dict[str, list[float]],
) -> tuple[np.ndarray, dict]:
    """Rigidly orient new points against shared public node coordinates."""
    node_ids = [node_id for node_id, _ in records]
    point_data = np.asarray(points, dtype=np.float64)
    if (
        len(node_ids) != len(set(node_ids))
        or point_data.shape != (len(records), 3)
        or not np.isfinite(point_data).all()
    ):
        raise ValueError("Semantic alignment inputs are invalid")
    indexes = [index for index, node_id in enumerate(node_ids) if node_id in prior]
    if len(indexes) < 4:
        raise ValueError("Prior semantic layout has too few shared nodes")
    current = point_data[indexes]
    target = np.asarray([prior[node_ids[index]] for index in indexes], dtype=np.float64)
    current_mean = current.mean(axis=0, keepdims=True)
    target_mean = target.mean(axis=0, keepdims=True)
    current_centered = current - current_mean
    target_centered = target - target_mean
    if (
        not np.isfinite(current).all()
        or not np.isfinite(target).all()
        or np.linalg.matrix_rank(current_centered) < 3
        or np.linalg.matrix_rank(target_centered) < 3
    ):
        raise ValueError("Prior semantic anchors are degenerate")
    left, _, right = np.linalg.svd(current_centered.T @ target_centered)
    rotation = left @ right
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-10):
        raise RuntimeError("Semantic alignment is not distance preserving")
    aligned = (point_data - current_mean) @ rotation
    aligned += target_mean
    before = np.sqrt(np.mean(np.sum((current_centered - target_centered) ** 2, axis=1)))
    matched = aligned[indexes]
    after = np.sqrt(np.mean(np.sum((matched - target) ** 2, axis=1)))
    reference = [[node_ids[index], *prior[node_ids[index]]] for index in indexes]
    reference_sha = hashlib.sha256(
        json.dumps(reference, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return aligned, {
        "method": "orthogonal-procrustes-3d-v1",
        "anchor_count": len(indexes),
        "reference_sha256": reference_sha,
        "determinant": round(float(np.linalg.det(rotation)), 6),
        "rmsd_before": round(float(before), 6),
        "rmsd_after": round(float(after), 6),
    }
