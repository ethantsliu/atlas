from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from ideas import build_provisional_ideas, score_feasibility, select_supporting_papers  # noqa: E402


def routed(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


class IdeaGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.papers = [
            {
                "id": "paper-1",
                "topics": [routed("agents")],
                "tricks": [routed("variance-control")],
            },
            {
                "id": "paper-2",
                "topics": [routed("agents")],
                "tricks": [routed("variance-control")],
            },
        ]

    def test_repo_free(self) -> None:
        ideas = build_provisional_ideas(self.papers)
        self.assertTrue(all(idea["repo_ids"] == [] for idea in ideas))
        self.assertTrue(all("feasibility" in idea for idea in ideas))

    def test_reading_priority(self) -> None:
        papers = [
            {"id": "paper-1", "stable_id": "arxiv:1", "reading_depth": "abstract"},
            {"id": "paper-2", "stable_id": "arxiv:1", "reading_depth": "metadata"},
            {"id": "paper-3", "stable_id": "arxiv:3", "reading_depth": "full_text"},
            {"id": "paper-4", "stable_id": "arxiv:4", "reading_depth": "verified"},
        ]

        selected = select_supporting_papers(papers, 3)

        self.assertEqual(
            [paper["id"] for paper in selected], ["paper-4", "paper-3", "paper-1"]
        )

    def test_topic_protocols(self) -> None:
        agent_brief = build_provisional_ideas(self.papers)[0]["brief"]
        environment_papers = [
            {
                "id": "paper-env",
                "topics": [routed("environment-design")],
                "tricks": [routed("evolutionary-search")],
            }
        ]
        environment_brief = build_provisional_ideas(environment_papers)[0]["brief"]
        self.assertNotEqual(agent_brief["evaluation"], environment_brief["evaluation"])
        self.assertIn("exploit gap", environment_brief["evaluation"][0])

    def test_score_shape(self) -> None:
        idea = {
            "topic_ids": ["agents"],
            "repo_ids": [],
            "origin": "cross-paper",
        }
        result = score_feasibility(idea)
        self.assertEqual(result["score"], round(result["score"], 1))
        self.assertEqual(len(result["factors"]), 5)
        self.assertGreaterEqual(result["score"], 1)
        self.assertLessEqual(result["score"], 10)
        self.assertLessEqual(result["score"], 7.0)
        self.assertTrue(result["screening_estimate"])


if __name__ == "__main__":
    unittest.main()
