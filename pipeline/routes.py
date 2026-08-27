"""Build and validate compact exact-cosine anchor routes."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from embed import EMBED_DIM, MODEL, MODEL_DIGEST


ROUTE_MAGIC = b"ATLASRT1"
ROUTE_COUNT = 8
ROUTE_HEAD = 80
ROUTE_PAIR = 4


def file_hash(path: Path) -> str:
    """Hash one immutable pipeline input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_digest(identifiers: list[str]) -> str:
    """Hash one ordered paper-row identity."""
    body = json.dumps(identifiers, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def load_node_ids(path: Path) -> set[str]:
    """Load the exact graph identities available to anchor routes."""
    try:
        atlas = json.loads(path.read_text(encoding="utf-8"))
        core = atlas["layout"]["positions"]
        asset = atlas["paper_asset"]
        digest = asset["sha256"]
        relative = asset["path"].removeprefix("/")
        if relative != f"data/papers/{digest}.json":
            raise RuntimeError("Atlas paper asset path is invalid")
        content = (path.parents[1] / relative).read_bytes()
        papers = json.loads(content)
        paper_positions = papers["layout"]["positions"]
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        AttributeError,
        IndexError,
        TypeError,
    ) as error:
        raise RuntimeError("Atlas anchor identities are invalid") from error
    if (
        not isinstance(core, dict)
        or not isinstance(paper_positions, dict)
        or asset.get("schema_version") != 1
        or papers.get("schema_version") != 1
        or asset.get("sha256") != hashlib.sha256(content).hexdigest()
        or asset.get("bytes") != len(content)
        or asset.get("paper_count") != len(papers.get("papers", []))
        or asset.get("paper_count") != len(paper_positions)
        or set(core).intersection(paper_positions)
        or len(core) + len(paper_positions) < ROUTE_COUNT
        or atlas["layout"].get("node_count") != len(core) + len(paper_positions)
        or any(
            not isinstance(identifier, str) or not identifier
            for identifier in (*core, *paper_positions)
        )
    ):
        raise RuntimeError("Atlas anchor identities are invalid")
    return set(core) | set(paper_positions)


def load_anchors(
    path: Path, node_ids: set[str] | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load ordered normalized anchors and require current graph identities."""
    try:
        with np.load(path) as bundle:
            schema = int(bundle["schema_version"])
            ids = np.asarray(bundle["ids"]).astype(str)
            vectors = np.asarray(bundle["vectors"], dtype=np.float32)
            points = np.asarray(bundle["points"], dtype=np.float32)
            model = str(bundle["model"])
            digest = str(bundle["model_digest"])
            dimensions = int(bundle["dimensions"])
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError("Archive semantic anchors are invalid") from error
    if (
        schema != 1
        or vectors.ndim != 2
        or vectors.shape[1] != EMBED_DIM
        or len(ids) != len(vectors)
        or len(ids) < ROUTE_COUNT
        or len(ids) > 65535
        or len(set(ids.tolist())) != len(ids)
        or any(not identifier or len(identifier) > 240 for identifier in ids)
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
    if node_ids is not None and set(ids.tolist()) != node_ids:
        raise RuntimeError("Archive semantic anchors do not match the atlas layout")
    return ids, vectors / norms, points


def anchor_bytes(ids: np.ndarray, anchor_sha256: str) -> bytes:
    """Publish ordered anchor identities without exposing embeddings."""
    payload = {
        "schema_version": 1,
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "anchor_sha256": anchor_sha256,
        "count": len(ids),
        "ids": ids.tolist(),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def project_points(
    vectors: np.ndarray,
    anchors: np.ndarray,
    points: np.ndarray,
    neighbors: int = ROUTE_COUNT,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project points and retain deterministic exact cosine anchor routes."""
    if len(vectors) == 0:
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, neighbors), dtype=np.uint16),
            np.empty((0, neighbors), dtype=np.uint16),
        )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("Archive embeddings contain zero vectors")
    normalized = vectors / norms
    output = np.empty((len(vectors), 3), dtype=np.float32)
    count = min(neighbors, len(anchors))
    route_indexes = np.empty((len(vectors), count), dtype=np.uint16)
    route_scores = np.empty((len(vectors), count), dtype=np.uint16)
    for start in range(0, len(vectors), 1024):
        stop = min(start + 1024, len(vectors))
        scores = normalized[start:stop] @ anchors.T
        thresholds = np.partition(scores, -count, axis=1)[:, -count]
        indexes = np.empty((len(scores), count), dtype=np.int64)
        for row, threshold in enumerate(thresholds):
            higher = np.flatnonzero(scores[row] > threshold)
            tied = np.flatnonzero(scores[row] == threshold)
            indexes[row] = np.concatenate((higher, tied[: count - len(higher)]))
        near = np.take_along_axis(scores, indexes, axis=1)
        quantized = np.rint((np.clip(near, -1, 1) + 1) * (65535 / 2)).astype(np.uint16)
        for row in range(len(indexes)):
            order = np.lexsort((indexes[row], -quantized[row].astype(np.int64)))
            indexes[row] = indexes[row, order]
            near[row] = near[row, order]
            quantized[row] = quantized[row, order]
        route_indexes[start:stop] = indexes
        route_scores[start:stop] = quantized
        weights = np.exp((near - near.max(axis=1, keepdims=True)) * 18)
        weights /= weights.sum(axis=1, keepdims=True)
        output[start:stop] = np.sum(points[indexes] * weights[..., None], axis=1)
    if not np.isfinite(output).all():
        raise RuntimeError("Archive semantic projection is invalid")
    return output, route_indexes, route_scores


def route_bytes(
    indexes: np.ndarray,
    scores: np.ndarray,
    identifiers: list[str],
    anchor_count: int,
    anchor_sha256: str,
) -> bytes:
    """Encode deterministic exact-cosine anchor routes by paper row."""
    shape = (len(identifiers), ROUTE_COUNT)
    if indexes.shape != shape or scores.shape != shape:
        raise ValueError("Archive route rows are misaligned")
    if (
        indexes.dtype != np.uint16
        or scores.dtype != np.uint16
        or np.any(indexes >= anchor_count)
    ):
        raise ValueError("Archive routes contain invalid anchors")
    pairs = np.empty((len(identifiers), ROUTE_COUNT, 2), dtype="<u2")
    pairs[:, :, 0] = indexes
    pairs[:, :, 1] = scores
    check_pairs(pairs, anchor_count)
    header = struct.pack(
        "<8sIHH32s32s",
        ROUTE_MAGIC,
        len(identifiers),
        ROUTE_COUNT,
        anchor_count,
        bytes.fromhex(row_digest(identifiers)),
        bytes.fromhex(anchor_sha256),
    )
    return header + pairs.tobytes()


def check_pairs(pairs: np.ndarray, anchor_count: int) -> None:
    """Require unique bounded routes in deterministic display order."""
    for route in pairs:
        values = [(int(pair[0]), int(pair[1])) for pair in route]
        if (
            any(index >= anchor_count for index, _score in values)
            or len({index for index, _score in values}) != ROUTE_COUNT
            or values != sorted(values, key=lambda value: (-value[1], value[0]))
        ):
            raise ValueError("Archive routes are invalid")


def check_routes(
    content: bytes,
    count: int,
    rows_sha256: str,
    anchor_count: int,
    anchor_sha256: str,
) -> None:
    """Validate one complete route asset against its release identities."""
    try:
        magic, route_count, neighbors, anchors, rows, anchor_digest = struct.unpack(
            "<8sIHH32s32s", content[:ROUTE_HEAD]
        )
    except struct.error as error:
        raise ValueError("Archive route contract drifted") from error
    if (
        magic != ROUTE_MAGIC
        or route_count != count
        or neighbors != ROUTE_COUNT
        or anchors != anchor_count
        or rows.hex() != rows_sha256
        or anchor_digest.hex() != anchor_sha256
        or len(content) != ROUTE_HEAD + route_count * ROUTE_COUNT * ROUTE_PAIR
    ):
        raise ValueError("Archive route contract drifted")
    pairs = np.frombuffer(content[ROUTE_HEAD:], dtype="<u2").reshape(
        route_count, ROUTE_COUNT, 2
    )
    check_pairs(pairs, anchor_count)
