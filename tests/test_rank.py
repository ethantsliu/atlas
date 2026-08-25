import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from rank import load_rules, rank_day, rank_paper, validate_rules


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")


def make_paper(**changes) -> dict:
    paper = {
        "id": "2608.00001",
        "url": "https://arxiv.org/abs/2608.00001",
        "title": "A precise optimization result",
        "abstract": "We prove a convergence theorem.",
        "authors": ["Ada Researcher"],
        "categories": ["math.OC"],
        "primary_category": "math.OC",
        "published": "2026-08-21T00:00:00Z",
        "updated": "2026-08-21T00:00:00Z",
        "comment": "",
    }
    return {**paper, **changes}


class RankTests(unittest.TestCase):
    def test_core_kept(self) -> None:
        ranked = rank_paper(make_paper(categories=["cs.LG"]), RULES)

        self.assertTrue(ranked["relevance"]["relevant"])
        self.assertEqual(ranked["relevance"]["lane"], "core")
        self.assertEqual(ranked["relevance"]["score"], 8.0)

    def test_field_kept(self) -> None:
        ranked = rank_paper(make_paper(categories=["cs.CL"]), RULES)

        self.assertTrue(ranked["relevance"]["relevant"])
        self.assertEqual(ranked["relevance"]["lane"], "field")

    def test_math_selective(self) -> None:
        ranked = rank_paper(
            make_paper(
                title="Generalization for deep learning",
                abstract="We study neural network sample complexity.",
            ),
            RULES,
        )

        self.assertTrue(ranked["relevance"]["relevant"])
        self.assertEqual(ranked["relevance"]["lane"], "math-stat")
        self.assertIn("deep learning", ranked["relevance"]["strong_hits"])

    def test_math_rejected(self) -> None:
        ranked = rank_paper(make_paper(), RULES)

        self.assertFalse(ranked["relevance"]["relevant"])
        self.assertEqual(ranked["relevance"]["lane"], "math-stat")

    def test_adjacent_signal(self) -> None:
        ranked = rank_paper(
            make_paper(
                categories=["q-bio.QM"],
                title="Deep learning and machine learning for cells",
            ),
            RULES,
        )

        self.assertTrue(ranked["relevance"]["relevant"])
        self.assertEqual(ranked["relevance"]["lane"], "adjacent")

    def test_interest_separate(self) -> None:
        ordinary = make_paper(id="2608.00001", categories=["cs.LG"])
        priority = make_paper(
            id="2608.00002",
            categories=["cs.LG"],
            title="Evolutionary search for environment generation",
            abstract="We introduce a world model benchmark using quality diversity.",
        )

        ranked = rank_day([ordinary, priority], RULES)

        self.assertEqual(
            [paper["id"] for paper in ranked], ["2608.00002", "2608.00001"]
        )
        self.assertGreater(
            ranked[0]["interest"]["score"], ranked[1]["interest"]["score"]
        )
        self.assertTrue(ranked[0]["topics"])
        self.assertTrue(ranked[0]["tricks"])

    def test_policy_rejected(self) -> None:
        invalid = {**RULES, "field_categories": ["cs.LG"]}

        with self.assertRaisesRegex(RuntimeError, "lanes overlap"):
            validate_rules(invalid)


if __name__ == "__main__":
    unittest.main()
