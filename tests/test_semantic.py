from __future__ import annotations

import sys
import copy
import unittest
from pathlib import Path

import numpy as np
from sklearn.manifold import trustworthiness

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from semantic import (  # noqa: E402
    cosine_top,
    ensure_quality,
    measure_quality,
    quality_report,
    quality_rows,
    recall_at,
    semantic_neighbors,
)
from validate import validate_clusters  # noqa: E402


def sample_vectors() -> np.ndarray:
    return np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
            [0.1, 0.9, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.1, 0.9],
        ],
        dtype=np.float32,
    )


class SemanticTests(unittest.TestCase):
    def test_cosine_precision(self) -> None:
        vectors = sample_vectors()

        indexes32, scores32 = cosine_top(vectors, count=2)
        indexes64, scores64 = cosine_top(vectors.astype(np.float64), count=2)

        self.assertTrue(np.array_equal(indexes32, indexes64))
        self.assertTrue(np.array_equal(scores32, scores64))
        self.assertEqual(scores32.dtype, np.float64)

    def test_sklearn_quality(self) -> None:
        random = np.random.default_rng(1729)
        vectors = random.normal(size=(14, 6))
        points = vectors[:, :3] + random.normal(scale=0.3, size=(14, 3))

        row_trust, _ = quality_rows(vectors, points, count=3)

        expected = trustworthiness(
            vectors,
            points,
            n_neighbors=3,
            metric="cosine",
        )
        self.assertAlmostEqual(float(np.mean(row_trust)), expected, places=12)

    def test_perfect_recall(self) -> None:
        vectors = sample_vectors()

        self.assertEqual(recall_at(vectors, vectors, count=1), 1.0)

    def test_quality_shape(self) -> None:
        vectors = sample_vectors()

        quality = measure_quality(vectors, vectors, count=1)

        self.assertEqual(quality["trustworthiness"], 1.0)
        self.assertEqual(quality["knn_recall"], 1.0)
        self.assertEqual(quality["k"], 1)

    def test_neighbor_order(self) -> None:
        vectors = sample_vectors()
        records = [(f"node-{index}", "") for index in range(len(vectors))]

        neighbors = semantic_neighbors(records, vectors, count=2)

        self.assertEqual(neighbors["node-0"][0]["id"], "node-1")
        self.assertNotIn("node-0", [item["id"] for item in neighbors["node-0"]])
        self.assertGreaterEqual(
            neighbors["node-0"][0]["score"],
            neighbors["node-0"][1]["score"],
        )

    def test_alias_filter(self) -> None:
        vectors = sample_vectors()
        records = [(f"node-{index}", "") for index in range(len(vectors))]

        neighbors = semantic_neighbors(
            records,
            vectors,
            count=1,
            exclusions={"node-0": {"node-1"}},
        )

        self.assertNotEqual(neighbors["node-0"][0]["id"], "node-1")

    def test_alias_oracle(self) -> None:
        vectors = np.asarray(
            [
                [1.0, 0.0],
                [0.99, 0.1],
                [0.0, 1.0],
                [0.1, 0.99],
                [-1.0, 0.0],
                [-0.99, -0.1],
            ],
            dtype=np.float32,
        )
        points = np.asarray([[0.0], [0.01], [0.1], [10.0], [20.0], [21.0]])
        blocked = [{1}, {0}, set(), set(), set(), set()]

        row_trust, row_recall = quality_rows(
            vectors,
            points,
            count=1,
            blocked=blocked,
        )

        np.testing.assert_allclose(
            row_trust,
            [2 / 3, 2 / 3, 3 / 4, 1.0, 1.0, 1.0],
        )
        np.testing.assert_array_equal(row_recall, [0, 0, 0, 1, 1, 1])

    def test_alias_shortage(self) -> None:
        vectors = np.eye(4, dtype=np.float32)
        records = [(f"node-{index}", "") for index in range(len(vectors))]

        with self.assertRaisesRegex(ValueError, "Too few non-alias neighbors"):
            semantic_neighbors(
                records,
                vectors,
                count=2,
                exclusions={"node-0": {"node-1", "node-2"}},
            )

        quality_vectors = np.eye(6, dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "Too few non-alias neighbors"):
            quality_rows(
                quality_vectors,
                quality_vectors,
                count=2,
                blocked=[{1, 2, 3, 4}, set(), set(), set(), set(), set()],
            )

    def test_tie_order(self) -> None:
        vectors = np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, -1.0], [-1.0, 0.0]],
            dtype=np.float32,
        )
        records = [(f"node-{index}", "") for index in range(len(vectors))]

        neighbors = semantic_neighbors(records, vectors, count=2)

        self.assertEqual(
            [item["id"] for item in neighbors["node-0"]],
            ["node-1", "node-2"],
        )

    def test_cohort_weighting(self) -> None:
        vectors = np.asarray(
            [
                [1.0, 0.0],
                [0.99, 0.1],
                [0.0, 1.0],
                [0.1, 0.99],
                [-1.0, 0.0],
                [-0.99, -0.1],
            ],
            dtype=np.float32,
        )
        points = np.asarray([[0.0], [0.01], [0.1], [10.0], [20.0], [21.0]])
        records = [(f"node-{index}", "") for index in range(len(vectors))]

        report = quality_report(
            records,
            vectors,
            points,
            {
                "small": {"node-0"},
                "large": {f"node-{index}" for index in range(1, 6)},
            },
            count=1,
            exclusions={"node-0": {"node-1"}, "node-1": {"node-0"}},
        )

        self.assertEqual(report["trustworthiness"], 0.847222)
        self.assertEqual(report["knn_recall"], 0.5)
        self.assertEqual(report["cohorts"]["small"]["trustworthiness"], 0.666667)
        self.assertEqual(report["cohorts"]["large"]["trustworthiness"], 0.883333)
        self.assertNotEqual(
            report["trustworthiness"],
            round(
                (
                    report["cohorts"]["small"]["trustworthiness"]
                    + report["cohorts"]["large"]["trustworthiness"]
                )
                / 2,
                6,
            ),
        )

    def test_quality_gate(self) -> None:
        quality = {
            "trustworthiness": 0.95,
            "knn_recall": 0.1,
            "thresholds": {"trustworthiness": 0.9, "knn_recall": 0.25},
        }

        with self.assertRaisesRegex(RuntimeError, "knn_recall"):
            ensure_quality(quality)

    def test_cohort_gate(self) -> None:
        quality = {
            "trustworthiness": 0.95,
            "knn_recall": 0.3,
            "thresholds": {"trustworthiness": 0.9, "knn_recall": 0.25},
            "cohorts": {
                "idea": {
                    "trustworthiness": 0.96,
                    "knn_recall": 0.2,
                    "thresholds": {"trustworthiness": 0.95, "knn_recall": 0.4},
                }
            },
        }

        with self.assertRaisesRegex(RuntimeError, "idea knn_recall"):
            ensure_quality(quality)

        quality["knn_recall"] = float("nan")
        with self.assertRaisesRegex(RuntimeError, "knn_recall"):
            ensure_quality(quality)


def cluster_fixture() -> tuple[dict, set[str]]:
    graph_ids = {f"node-{index}" for index in range(60)}
    clusters = []
    assignments = {}
    for cluster_index in range(4):
        members = [f"node-{cluster_index * 15 + offset}" for offset in range(15)]
        cluster_id = f"cluster-{cluster_index}"
        clusters.append(
            {
                "id": cluster_id,
                "label": f"region {cluster_index}",
                "label_source": "one-to-one taxonomy match",
                "label_similarity": 0.6,
                "centroid": [float(cluster_index), 0.0, 0.0],
                "count": 15,
                "radius": 1.0,
                "medoid": members[0],
                "spread": 0.2,
                "terms": [f"region {cluster_index}"],
            }
        )
        assignments.update({node_id: cluster_id for node_id in members})
    return (
        {
            "cluster_method": "embedding-normalized-kmeans-v1",
            "cluster_kind": "coarse embedding neighborhoods",
            "cluster_quality": {
                "inertia": 12.0,
                "mean_inertia": 0.2,
                "silhouette": 0.1,
                "stability_ari": 0.5,
                "fit_count": 60,
                "silhouette_count": 60,
                "thresholds": {"silhouette": 0.0, "stability_ari": 0.2},
                "min_count": 15,
                "max_share": 0.25,
            },
            "clusters": clusters,
            "node_clusters": assignments,
        },
        graph_ids,
    )


class ClusterValidationTests(unittest.TestCase):
    def test_valid_clusters(self) -> None:
        layout, graph_ids = cluster_fixture()

        validate_clusters(layout, graph_ids, 60)

    def test_missing_coverage(self) -> None:
        layout, graph_ids = cluster_fixture()
        layout["node_clusters"].pop("node-59")

        with self.assertRaisesRegex(RuntimeError, "cover"):
            validate_clusters(layout, graph_ids, 60)

    def test_bad_reference(self) -> None:
        layout, graph_ids = cluster_fixture()
        layout["node_clusters"]["node-0"] = "cluster-missing"

        with self.assertRaisesRegex(RuntimeError, "references"):
            validate_clusters(layout, graph_ids, 60)

    def test_stale_count(self) -> None:
        layout, graph_ids = cluster_fixture()
        layout = copy.deepcopy(layout)
        layout["clusters"][0]["count"] = 14

        with self.assertRaisesRegex(RuntimeError, "count is stale"):
            validate_clusters(layout, graph_ids, 60)

    def test_weak_label(self) -> None:
        layout, graph_ids = cluster_fixture()
        layout["clusters"][0]["label_similarity"] = 0.1

        with self.assertRaisesRegex(RuntimeError, "label similarity"):
            validate_clusters(layout, graph_ids, 60)


if __name__ == "__main__":
    unittest.main()
