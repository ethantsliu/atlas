from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from cluster import _markers, build_clusters  # noqa: E402


def sample_data() -> tuple[list[tuple[str, str]], np.ndarray, np.ndarray]:
    records = [
        (
            "topic:worlds",
            "machine learning research area: world models. "
            "Representative work: latent dynamics",
        ),
        ("paper-world", "research paper: latent world models for robot control"),
        ("paper-dynamics", "research paper: predictive dynamics and simulators"),
        (
            "trick:preference",
            "machine learning method: preference optimization. "
            "Representative work: human feedback",
        ),
        ("paper-reward", "research paper: preference reward model alignment"),
        ("paper-feedback", "research paper: aligning models with human feedback"),
    ]
    vectors = np.asarray(
        [
            [1.00, 0.02, 0.00, 0.00],
            [0.98, 0.08, 0.00, 0.00],
            [0.94, 0.12, 0.02, 0.00],
            [0.00, 0.00, 1.00, 0.02],
            [0.00, 0.04, 0.98, 0.08],
            [0.02, 0.00, 0.94, 0.12],
        ],
        dtype=np.float32,
    )
    points = np.asarray(
        [
            [-10, 0, 0],
            [-12, 2, 0],
            [-8, -2, 1],
            [10, 0, 0],
            [12, 2, 0],
            [8, -2, -1],
        ],
        dtype=np.float32,
    )
    return records, vectors, points


class ClusterTests(unittest.TestCase):
    def test_semantic_groups(self) -> None:
        records, vectors, points = sample_data()

        result = build_clusters(records, vectors, points, cluster_count=2)

        assignments = result["node_clusters"]
        self.assertEqual(assignments["topic:worlds"], assignments["paper-world"])
        self.assertEqual(assignments["paper-world"], assignments["paper-dynamics"])
        self.assertEqual(assignments["trick:preference"], assignments["paper-reward"])
        self.assertNotEqual(assignments["paper-world"], assignments["paper-reward"])

    def test_region_metadata(self) -> None:
        records, vectors, points = sample_data()

        result = build_clusters(records, vectors, points, cluster_count=2)

        self.assertEqual(result["cluster_method"], "embedding-normalized-kmeans-v1")
        self.assertEqual(sum(row["count"] for row in result["clusters"]), 6)
        self.assertEqual(set(result["node_clusters"]), {item[0] for item in records})
        self.assertEqual(result["cluster_kind"], "coarse embedding neighborhoods")
        self.assertEqual(result["cluster_quality"]["fit_count"], 4)
        self.assertEqual(result["cluster_quality"]["silhouette_count"], 4)
        self.assertGreaterEqual(result["cluster_quality"]["silhouette"], -1)
        self.assertGreaterEqual(result["cluster_quality"]["stability_ari"], -1)
        self.assertEqual(
            result["cluster_quality"]["thresholds"],
            {"silhouette": 0.0, "stability_ari": 0.2},
        )
        self.assertEqual(
            len({row["label"] for row in result["clusters"]}),
            len(result["clusters"]),
        )
        for row in result["clusters"]:
            self.assertEqual(len(row["centroid"]), 3)
            self.assertGreater(row["radius"], 0)
            self.assertGreaterEqual(row["spread"], 0)
            self.assertIn(row["medoid"], result["node_clusters"])
            self.assertTrue(row["terms"])
            self.assertLessEqual(len(row["terms"]), 5)
            self.assertEqual(row["label"], row["label"].lower())
            self.assertEqual(row["label_source"], "one-to-one taxonomy match")
            self.assertGreaterEqual(row["label_similarity"], 0.3)
            self.assertNotIn("indexes", row)

    def test_taxonomy_labels(self) -> None:
        records, vectors, points = sample_data()

        result = build_clusters(records, vectors, points, cluster_count=2)

        labels = {row["label"] for row in result["clusters"]}
        self.assertEqual(labels, {"world models", "preference optimization"})
        self.assertFalse(labels & {"neural", "does", "collection", "systems"})

    def test_bare_labels(self) -> None:
        records, vectors, points = sample_data()
        records[0] = ("topic:worlds", "world models")
        records[3] = ("trick:preference", "preference optimization")

        result = build_clusters(records, vectors, points, cluster_count=2)

        self.assertEqual(
            {row["label"] for row in result["clusters"]},
            {"world models", "preference optimization"},
        )
        self.assertEqual(result["cluster_quality"]["fit_count"], 4)

    def test_repeatable_output(self) -> None:
        records, vectors, points = sample_data()

        first = build_clusters(records, vectors, points, cluster_count=2)
        second = build_clusters(records, vectors, points, cluster_count=2)

        self.assertEqual(first, second)

    def test_mapping_records(self) -> None:
        records = [
            {"id": "one", "title": "one model"},
            {"id": "two", "text": "two model"},
        ]
        vectors = np.asarray([[1, 0], [0.9, 0.1]], dtype=np.float32)
        points = np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32)

        result = build_clusters(records, vectors, points, cluster_count=1)

        self.assertEqual(result["clusters"][0]["count"], 2)

    def test_empty_input(self) -> None:
        result = build_clusters([], np.empty((0, 4)), np.empty((0, 3)))

        self.assertEqual(result["clusters"], [])
        self.assertEqual(result["node_clusters"], {})

    def test_context_excluded(self) -> None:
        records, vectors, points = sample_data()
        records.append(("context-one", "collection entry: title-only metadata"))
        vectors = np.vstack([vectors, np.asarray([[0.9, 0.1, 0, 0]])])
        points = np.vstack([points, np.asarray([[-9, 1, 0]])])

        result = build_clusters(records, vectors, points, cluster_count=2)

        self.assertEqual(result["cluster_quality"]["fit_count"], 4)
        self.assertIn("context-one", result["node_clusters"])

    def test_bad_inputs(self) -> None:
        records, vectors, points = sample_data()

        with self.assertRaisesRegex(ValueError, "align"):
            build_clusters(records, vectors[:-1], points)
        with self.assertRaisesRegex(ValueError, "non-zero"):
            build_clusters(records, np.zeros_like(vectors), points)
        with self.assertRaisesRegex(ValueError, "Cluster count"):
            build_clusters(records, vectors, points, cluster_count=7)

    def test_weak_labels(self) -> None:
        records, vectors, points = sample_data()
        vectors[0] = -vectors[0]
        vectors[3] = -vectors[3]

        with self.assertRaisesRegex(RuntimeError, "weak or generic"):
            build_clusters(records, vectors, points, cluster_count=2)

    def test_gate_assignment(self) -> None:
        records = [("topic:worlds", "world models"), ("topic:align", "alignment")]
        vectors = np.asarray([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
        centers = np.asarray(
            [
                [0.31, 0.9, np.sqrt(1 - 0.31**2 - 0.9**2)],
                [0.29, 0.31, np.sqrt(1 - 0.29**2 - 0.31**2)],
            ],
            dtype=np.float32,
        )

        markers = _markers(
            [record[0] for record in records],
            [record[1] for record in records],
            vectors,
            centers,
        )

        self.assertEqual(markers[0][0], "world models")
        self.assertEqual(markers[1][0], "alignment")
        self.assertTrue(all(score >= 0.3 for _, score in markers.values()))

    def test_generic_excluded(self) -> None:
        records = [
            ("trick:adam", "adam"),
            ("topic:worlds", "world models"),
            ("topic:align", "alignment"),
        ]
        vectors = np.eye(3, dtype=np.float32)
        centers = np.asarray(
            [
                [0.8, 0.5, 0.1],
                [0.7, 0.1, 0.5],
            ],
            dtype=np.float32,
        )

        markers = _markers(
            [record[0] for record in records],
            [record[1] for record in records],
            vectors,
            centers,
        )

        self.assertEqual(
            {label for label, _ in markers.values()},
            {"alignment", "world models"},
        )

    def test_quality_gate(self) -> None:
        records, vectors, points = sample_data()

        with patch("cluster.adjusted_rand_score", return_value=0.1):
            with self.assertRaisesRegex(RuntimeError, "quality thresholds"):
                build_clusters(records, vectors, points, cluster_count=2)


if __name__ == "__main__":
    unittest.main()
