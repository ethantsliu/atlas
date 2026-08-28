from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from ideas import (  # noqa: E402
    LEGACY_IDS,
    build_cross_ideas,
    build_provisional_ideas,
    idea_id,
    idea_title,
)


def routed(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(identifier: str, stable_id: str | None = None) -> dict:
    return {
        "id": identifier,
        "stable_id": stable_id,
        "reading_depth": "abstract",
        "topics": [routed("agents")],
        "tricks": [routed("variance-control")],
    }


class IdeaIdTests(unittest.TestCase):
    def test_published_set(self) -> None:
        atlas = json.loads(
            (
                Path(__file__).resolve().parents[1] / "data/generated/atlas.json"
            ).read_text()
        )
        papers = [
            paper
            for paper in atlas["papers"]
            if paper.get("record_kind") != "non_paper_context"
        ]
        expected = {
            (idea["topic_ids"][0], idea["trick_ids"][0]): idea["id"]
            for idea in atlas["ideas"]
            if idea["origin"] == "cross-paper"
        }
        generated = build_provisional_ideas(papers)
        actual = {
            (idea["topic_ids"][0], idea["trick_ids"][0]): idea["id"]
            for idea in generated
        }

        self.assertEqual(actual, expected)

    def test_support_gate(self) -> None:
        papers = [
            paper("paper-1", "arxiv:1"),
            paper("paper-copy", "arxiv:1"),
        ]

        self.assertEqual(build_provisional_ideas(papers), [])

    def test_single_vote(self) -> None:
        first = paper("paper-1", "arxiv:1")
        first["topics"].append(routed("agents"))
        first["tricks"].append(routed("variance-control"))
        ideas = build_provisional_ideas([first, paper("paper-2", "arxiv:2")])

        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["id"], "idea-standalone-agents--variance-control")
        self.assertEqual(ideas[0]["brief"]["paper_ids"], ["paper-1", "paper-2"])

    def test_stable_id(self) -> None:
        support = [paper("paper-1", "arxiv:1"), paper("paper-2", "arxiv:2")]
        base = build_cross_ideas({("multimodal", "low-rank-adaptation"): support})[0]
        ranked = build_cross_ideas(
            {
                ("alignment", "regularization"): [
                    paper("paper-3", "arxiv:3"),
                    paper("paper-4", "arxiv:4"),
                    paper("paper-5", "arxiv:5"),
                ],
                ("Multimodal", "low_rank_adaptation"): list(reversed(support)),
            }
        )
        matched = next(idea for idea in ranked if idea["topic_ids"] == ["multimodal"])

        self.assertEqual(matched["id"], base["id"])
        self.assertEqual(matched["id"], "idea-standalone-45")

    def test_legacy_pair(self) -> None:
        self.assertEqual(
            set(LEGACY_IDS.values()),
            {f"idea-standalone-{index}" for index in range(1, 49)},
        )
        self.assertEqual(
            idea_id("multimodal", "low-rank-adaptation"), "idea-standalone-45"
        )
        self.assertEqual(
            idea_id("agents", "variance-control"),
            "idea-standalone-agents--variance-control",
        )

    def test_titles(self) -> None:
        self.assertEqual(
            idea_title("agents", "variance-control"),
            "When does variance control make agents more reliable?",
        )
        self.assertEqual(
            idea_title("new-field", "regularization"),
            "Where does regularization produce a repeatable gain in new field?",
        )

    def test_all_pairs(self) -> None:
        pairs = {
            (f"topic-{index}", "regularization"): [
                paper(f"paper-{index}-a", f"arxiv:{index}-a"),
                paper(f"paper-{index}-b", f"arxiv:{index}-b"),
            ]
            for index in range(49)
        }

        ideas = build_cross_ideas(pairs)

        self.assertEqual(len(ideas), len(pairs))
        self.assertEqual(
            {(idea["topic_ids"][0], idea["trick_ids"][0]) for idea in ideas},
            set(pairs),
        )


if __name__ == "__main__":
    unittest.main()
