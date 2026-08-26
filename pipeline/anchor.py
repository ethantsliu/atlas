#!/usr/bin/env python3
"""Publish stable semantic anchors for incremental archive projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from embed import CACHE_PATH, EMBED_DIM, MODEL, MODEL_DIGEST, valid_vectors
from layout import OLLAMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = ROOT / "data/generated/layout.json"
ANCHOR_PATH = ROOT / "data/source/anchors.npz"


def parse_args() -> argparse.Namespace:
    """Parse explicit source and destination paths."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=Path, default=CACHE_PATH)
    parser.add_argument("--layout", type=Path, default=LAYOUT_PATH)
    parser.add_argument("--output", type=Path, default=ANCHOR_PATH)
    return parser.parse_args()


def build_anchors(vectors_path: Path, layout_path: Path, output: Path) -> int:
    """Align verified embeddings with their immutable public 3D coordinates."""
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    positions = layout.get("positions", {})
    with np.load(vectors_path) as cached:
        ids = np.asarray(cached["ids"]).astype(str)
        vectors = np.asarray(cached["vectors"], dtype=np.float32)
        vector_sha = str(cached["vector_sha256"])
        if not valid_vectors(vectors, vector_sha) or len(ids) != len(vectors):
            raise RuntimeError("Semantic vector cache is invalid")
        indexes = [index for index, node_id in enumerate(ids) if node_id in positions]
        anchor_ids = ids[indexes]
        anchor_vectors = vectors[indexes]
        anchor_points = np.asarray(
            [positions[node_id] for node_id in anchor_ids], dtype=np.float32
        )
    if (
        anchor_points.shape != (len(anchor_ids), 3)
        or len(anchor_ids) < 100
        or not np.isfinite(anchor_points).all()
    ):
        raise RuntimeError("Semantic anchor coordinates are invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.npz")
    np.savez_compressed(
        temporary,
        schema_version=1,
        model=MODEL,
        model_digest=MODEL_DIGEST,
        runtime=f"ollama-{OLLAMA_VERSION}",
        dimensions=EMBED_DIM,
        ids=anchor_ids,
        vectors=anchor_vectors,
        points=anchor_points,
    )
    temporary.replace(output)
    return len(anchor_ids)


def main() -> None:
    """Build the portable anchor bundle."""
    args = parse_args()
    count = build_anchors(args.vectors, args.layout, args.output)
    print(f"Published {count:,} stable semantic anchors")


if __name__ == "__main__":
    main()
