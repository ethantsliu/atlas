from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from audit import audit_layout  # noqa: E402
from cluster import build_clusters  # noqa: E402
from embed import (  # noqa: E402
    alias_exclusions,
    cohort_ids,
    node_records,
    row_hash,
    vector_hash,
    vector_sha,
)
from mix import mix_report  # noqa: E402
from semantic import NEIGHBOR_COUNT, quality_report, semantic_neighbors  # noqa: E402


def sample_atlas() -> dict:
    papers = [
        {
            "id": f"paper-{index}",
            "title": f"{'World' if index < 10 else 'Preference'} model {index}",
            "record_kind": "paper",
            "reading": {
                "problem": "Model dynamics" if index < 10 else "Model rewards",
                "approach": "Predict states" if index < 10 else "Rank responses",
            },
            "topics": [{"id": "worlds" if index < 10 else "preferences"}],
            "tricks": [],
        }
        for index in range(20)
    ]
    papers.append(
        {
            "id": "context-1",
            "title": "World model context",
            "record_kind": "non_paper_context",
            "reading": {},
            "topics": [{"id": "worlds"}],
            "tricks": [],
        }
    )
    return {
        "topics": [
            {"id": "worlds", "label": "world models"},
            {"id": "preferences", "label": "preference optimization"},
        ],
        "tricks": [],
        "papers": papers,
        "ideas": [
            {
                "id": "idea-world",
                "topic_ids": ["worlds"],
                "trick_ids": [],
                "brief": {"title": "World environments", "thesis": "Predict worlds"},
            },
            {
                "id": "idea-preference",
                "topic_ids": ["preferences"],
                "trick_ids": [],
                "brief": {"title": "Preference signals", "thesis": "Rank outcomes"},
            },
        ],
    }


def sample_vectors(records: list[tuple[str, str]]) -> tuple[np.ndarray, np.ndarray]:
    vectors = np.zeros((len(records), 4), dtype=np.float32)
    points = np.zeros((len(records), 3), dtype=np.float32)
    for index, (node_id, _) in enumerate(records):
        preference = "preference" in node_id or node_id.startswith("paper-1")
        offset = (index % 10) / 100
        vectors[index, int(preference)] = 1
        vectors[index, 2] = offset
        vectors[index, 3] = offset * offset
        points[index] = [20 if preference else -20, offset * 100, offset * offset]
    return vectors, points


def sample_layout(atlas: dict) -> tuple[dict, np.ndarray]:
    records = node_records(atlas)
    vectors, points = sample_vectors(records)
    exclusions = alias_exclusions(atlas, records)
    positions = {
        node_id: [float(value) for value in point]
        for (node_id, _), point in zip(records, points, strict=True)
    }
    neighbors = semantic_neighbors(records, vectors, exclusions=exclusions)
    layout = {
        "embedding": {
            "model": "fixture-model",
            "artifact_sha256": "a" * 64,
            "dimensions": vectors.shape[1],
            "input_sha256": vector_hash(records),
            "vector_sha256": vector_sha(vectors),
        },
        "reducer": {"name": "fixture"},
        "neighbor_count": NEIGHBOR_COUNT,
        "neighbors": neighbors,
        "quality": quality_report(
            records,
            vectors,
            points,
            cohort_ids(atlas, records),
            exclusions=exclusions,
        ),
        "positions": positions,
        "mix_quality": mix_report(atlas, neighbors, positions),
        **build_clusters(records, vectors, points),
    }
    return layout, vectors


def write_cache(path: Path, atlas: dict, layout: dict, vectors: np.ndarray) -> None:
    records = node_records(atlas)
    np.savez_compressed(
        path,
        digest=vector_hash(records),
        model=layout["embedding"]["model"],
        model_digest=layout["embedding"]["artifact_sha256"],
        dimensions=vectors.shape[1],
        ids=np.asarray([node_id for node_id, _ in records]),
        row_hashes=np.asarray([row_hash(record) for record in records]),
        vector_sha256=vector_sha(vectors),
        vectors=vectors,
    )


class AuditTests(unittest.TestCase):
    def test_exact_artifacts(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            before = path.read_bytes()

            audit_layout(atlas, {}, path, layout)

            self.assertEqual(path.read_bytes(), before)

    def test_vector_sha(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            with np.load(path) as saved:
                values = {field: saved[field] for field in saved.files}
            values["vectors"] = vectors.copy()
            values["vectors"][0, 0] += 0.25
            np.savez_compressed(path, **values)

            with self.assertRaisesRegex(RuntimeError, "cache SHA"):
                audit_layout(atlas, {}, path, layout)

    def test_layout_sha(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        layout["embedding"]["vector_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)

            with self.assertRaisesRegex(RuntimeError, "Layout vector SHA"):
                audit_layout(atlas, {}, path, layout)

    def test_cache_order(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            with np.load(path) as saved:
                values = {field: saved[field] for field in saved.files}
            values["ids"] = values["ids"][::-1]
            np.savez_compressed(path, **values)

            with self.assertRaisesRegex(RuntimeError, "row hashes"):
                audit_layout(atlas, {}, path, layout)

    def test_cache_superset(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        extra = np.full((1, vectors.shape[1]), 0.5, dtype=np.float32)
        expanded = np.vstack([vectors, extra])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            with np.load(path) as saved:
                values = {field: saved[field] for field in saved.files}
            values["digest"] = "superset"
            values["ids"] = np.append(values["ids"], "idea-unfitted")
            values["row_hashes"] = np.append(
                values["row_hashes"], row_hash(("idea-unfitted", "extra"))
            )
            values["vectors"] = expanded
            values["vector_sha256"] = vector_sha(expanded)
            np.savez_compressed(path, **values)

            audit_layout(atlas, {}, path, layout)

            values["ids"] = np.append(values["ids"][:-2], "idea-unfitted")
            values["row_hashes"] = np.append(
                values["row_hashes"][:-2], row_hash(("idea-unfitted", "extra"))
            )
            values["vectors"] = np.vstack([vectors[:-1], extra])
            values["vector_sha256"] = vector_sha(values["vectors"])
            np.savez_compressed(path, **values)
            with self.assertRaisesRegex(RuntimeError, "missing fitted"):
                audit_layout(atlas, {}, path, layout)

    def test_cache_duplicate(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            with np.load(path) as saved:
                values = {field: saved[field] for field in saved.files}
            values["ids"] = values["ids"].copy()
            values["ids"][1] = values["ids"][0]
            np.savez_compressed(path, **values)

            with self.assertRaisesRegex(RuntimeError, "row IDs"):
                audit_layout(atlas, {}, path, layout)

    def test_cache_row(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            with np.load(path) as saved:
                values = {field: saved[field] for field in saved.files}
            values["row_hashes"] = values["row_hashes"].copy()
            values["row_hashes"][0] = "0" * 64
            np.savez_compressed(path, **values)

            with self.assertRaisesRegex(RuntimeError, "row hashes"):
                audit_layout(atlas, {}, path, layout)

    def test_score_quantum(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            changed = copy.deepcopy(layout)
            row = changed["neighbors"]["paper-0"][0]
            row["score"] = round(row["score"] + 0.000001, 6)
            audit_layout(atlas, {}, path, changed)

            row["score"] = round(row["score"] + 0.000002, 6)
            with self.assertRaisesRegex(RuntimeError, "exact neighbors"):
                audit_layout(atlas, {}, path, changed)

    def test_derived_drift(self) -> None:
        atlas = sample_atlas()
        layout, vectors = sample_layout(atlas)
        cases = (
            ("neighbors", lambda value: value["paper-0"].reverse()),
            (
                "quality",
                lambda value: value["cohorts"]["paper"].update({"knn_recall": 0.0}),
            ),
            ("clusters", lambda value: value[0].update({"radius": 999.0})),
            (
                "mix_quality",
                lambda value: value.update({"position_eta_squared": 0.0}),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            write_cache(path, atlas, layout, vectors)
            for field, change in cases:
                changed = copy.deepcopy(layout)
                change(changed[field])
                with self.subTest(field=field):
                    message = "mixing" if field == "mix_quality" else field.rstrip("s")
                    with self.assertRaisesRegex(RuntimeError, message):
                        audit_layout(atlas, {}, path, changed)


if __name__ == "__main__":
    unittest.main()
