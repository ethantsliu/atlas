from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from place import base_atlas, build_places, validate_places  # noqa: E402


def fixture() -> tuple[dict, dict]:
    atlas = {
        "topics": [{"id": "worlds"}],
        "tricks": [{"id": "search"}],
        "papers": [
            {"id": "paper-1", "stable_id": "arxiv:1"},
            {"id": "paper-2", "stable_id": "arxiv:2"},
        ],
        "ideas": [
            {"id": "idea-fit", "topic_ids": [], "trick_ids": [], "brief": {}},
            {
                "id": "idea-new",
                "topic_ids": ["worlds"],
                "trick_ids": ["search"],
                "brief": {"paper_ids": ["arxiv:1", "arxiv:2"]},
            },
        ],
    }
    positions = {
        "topic:worlds": [10.0, 0.0, 0.0],
        "trick:search": [0.0, 10.0, 0.0],
        "paper-1": [0.0, 0.0, 10.0],
        "paper-2": [0.0, 0.0, 20.0],
        "idea-fit": [5.0, 5.0, 5.0],
    }
    layout = {
        "method": "embedding-umap-3d-v1",
        "node_count": len(positions),
        "positions": positions,
        "node_clusters": {node_id: "region-one" for node_id in positions},
    }
    return atlas, layout


class PlaceTests(unittest.TestCase):
    def test_deterministic_overlay(self) -> None:
        atlas, layout = fixture()
        before = deepcopy(layout)

        first = build_places(atlas, layout)
        second = build_places(deepcopy(atlas), deepcopy(layout))

        self.assertEqual(first, second)
        self.assertEqual(layout, before)
        self.assertEqual(first["node_count"], 1)
        self.assertEqual(set(first["positions"]), {"idea-new"})
        self.assertEqual(
            first["neighbors"]["idea-new"],
            ["paper-1", "paper-2", "topic:worlds", "trick:search"],
        )
        self.assertEqual(first["node_clusters"]["idea-new"], "region-one")
        self.assertNotIn(
            tuple(first["positions"]["idea-new"]),
            {tuple(point) for point in layout["positions"].values()},
        )

    def test_fitted_subset(self) -> None:
        atlas, layout = fixture()
        atlas["idea_layout"] = build_places(atlas, layout)

        fitted = base_atlas(atlas)

        self.assertEqual([idea["id"] for idea in fitted["ideas"]], ["idea-fit"])
        self.assertEqual(len(atlas["ideas"]), 2)

    def test_stale_overlay(self) -> None:
        atlas, layout = fixture()
        atlas["layout"] = layout
        atlas["idea_layout"] = build_places(atlas, layout)

        validate_places(atlas)
        atlas["idea_layout"]["positions"]["idea-new"][0] += 1
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_places(atlas)

    def test_requires_anchors(self) -> None:
        atlas, layout = fixture()
        atlas["ideas"][1]["topic_ids"] = ["missing"]
        atlas["ideas"][1]["trick_ids"] = []
        atlas["ideas"][1]["brief"]["paper_ids"] = []

        with self.assertRaisesRegex(ValueError, "no fitted anchors"):
            build_places(atlas, layout)


if __name__ == "__main__":
    unittest.main()
