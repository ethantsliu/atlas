from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from mix import (  # noqa: E402
    ROUTE_THRESHOLDS,
    duplicate_count,
    ensure_mix,
    kind_eta,
    mix_report,
    point_rankings,
    route_metrics,
)


def route_fixture() -> tuple[dict, dict, dict]:
    papers = [
        {
            "id": f"paper-{index}",
            "record_kind": "paper",
            "topics": [{"id": "worlds"}] if index < 4 else [],
            "tricks": [{"id": "search"}] if index >= 4 else [],
        }
        for index in range(8)
    ]
    atlas = {
        "topics": [{"id": "worlds"}],
        "tricks": [{"id": "search"}],
        "papers": papers,
        "ideas": [],
    }
    ids = [paper["id"] for paper in papers]
    rankings = {
        "topic:worlds": ids,
        "trick:search": list(reversed(ids)),
    }
    neighbors = {
        node_id: [
            {"id": other_id, "score": round(1 - index / 10, 6)}
            for index, other_id in enumerate(entries)
        ]
        for node_id, entries in rankings.items()
    }
    positions = {
        "topic:worlds": [-2.0, 0.0, 0.0],
        "trick:search": [2.0, 0.0, 0.0],
        **{
            f"paper-{index}": [
                -2.0 + (index + 1) / 100 if index < 4 else 2.0 + (index + 1) / 100,
                index / 1000,
                index / 10000,
            ]
            for index in range(8)
        },
    }
    return atlas, neighbors, positions


def valid_report() -> dict:
    routes = {
        "topic": {"node_count": 1, "precision": 0.25, "hit_rate": 1.0},
        "trick": {"node_count": 1, "precision": 0.25, "hit_rate": 1.0},
        "combined": {"node_count": 2, "precision": 0.3, "hit_rate": 1.0},
    }
    return {
        "semantic_routes": copy.deepcopy(routes),
        "projected_routes": copy.deepcopy(routes),
        "position_eta_squared": 0.04,
        "exact_coordinate_duplicates": 0,
    }


class RouteTests(unittest.TestCase):
    def test_separate_metrics(self) -> None:
        atlas, neighbors, positions = route_fixture()
        rankings = {
            node_id: [entry["id"] for entry in entries]
            for node_id, entries in neighbors.items()
        }

        metrics = route_metrics(atlas, rankings)
        projected = point_rankings(positions, set(rankings))

        self.assertEqual(
            metrics["topic"], {"node_count": 1, "precision": 0.5, "hit_rate": 1.0}
        )
        self.assertEqual(
            metrics["trick"], {"node_count": 1, "precision": 0.5, "hit_rate": 1.0}
        )
        self.assertEqual(set(projected), set(rankings))

    def test_report_contract(self) -> None:
        atlas, neighbors, positions = route_fixture()
        report = mix_report(atlas, neighbors, positions)

        self.assertEqual(report["kind"], "cross-kind-layout-v1")
        self.assertEqual(report["thresholds"]["routes"], ROUTE_THRESHOLDS)
        self.assertEqual(report["exact_coordinate_duplicates"], 0)

    def test_each_gate(self) -> None:
        ensure_mix(valid_report())
        cases = (
            ("semantic_routes", "topic", "precision", 0.19, "Semantic topic"),
            ("semantic_routes", "trick", "hit_rate", 0.74, "Semantic trick"),
            ("projected_routes", "combined", "precision", 0.29, "Projected combined"),
        )
        for space, kind, metric, value, message in cases:
            report = valid_report()
            report[space][kind][metric] = value
            with self.subTest(space=space, kind=kind, metric=metric):
                with self.assertRaisesRegex(RuntimeError, message):
                    ensure_mix(report)


class MixingTests(unittest.TestCase):
    def test_kind_eta(self) -> None:
        atlas = {
            "topics": [{"id": "one"}, {"id": "two"}],
            "tricks": [{"id": "one"}, {"id": "two"}],
            "papers": [
                {"id": "paper-1", "record_kind": "paper"},
                {"id": "paper-2", "record_kind": "paper"},
                {"id": "context-1", "record_kind": "non_paper_context"},
                {"id": "context-2", "record_kind": "non_paper_context"},
            ],
            "ideas": [{"id": "idea-1"}, {"id": "idea-2"}],
        }
        mixed = {
            "topic:one": [-1.0, 0.0, 0.0],
            "topic:two": [1.0, 0.0, 0.0],
            "trick:one": [-1.0, 0.01, 0.0],
            "trick:two": [1.0, 0.01, 0.0],
            "paper-1": [-1.0, 0.02, 0.0],
            "paper-2": [1.0, 0.02, 0.0],
            "context-1": [-1.0, 0.03, 0.0],
            "context-2": [1.0, 0.03, 0.0],
            "idea-1": [-1.0, 0.04, 0.0],
            "idea-2": [1.0, 0.04, 0.0],
        }
        kinds = (
            "topic",
            "topic",
            "trick",
            "trick",
            "paper",
            "paper",
            "context",
            "context",
            "idea",
            "idea",
        )
        banded = {}
        for index, (node_id, kind) in enumerate(zip(mixed, kinds, strict=True)):
            center = ("topic", "trick", "paper", "context", "idea").index(kind) * 10
            banded[node_id] = [float(center + (-1 if index % 2 == 0 else 1)), 0, 0]

        self.assertLess(kind_eta(atlas, mixed), kind_eta(atlas, banded))

    def test_duplicate_gate(self) -> None:
        self.assertEqual(duplicate_count({"a": [0, 0, 0], "b": [0.0, 0.0, 0.0]}), 1)
        report = valid_report()
        report["exact_coordinate_duplicates"] = 1
        with self.assertRaisesRegex(RuntimeError, "exact coordinate"):
            ensure_mix(report)

    def test_eta_gate(self) -> None:
        report = valid_report()
        report["position_eta_squared"] = 0.051
        with self.assertRaisesRegex(RuntimeError, "positional variance"):
            ensure_mix(report)


if __name__ == "__main__":
    unittest.main()
