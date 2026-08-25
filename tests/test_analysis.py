from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from analysis import compact_paper, summarize_abstract  # noqa: E402
from assets import reading_public_path  # noqa: E402


class PaperAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = {
            "id": 7,
            "stable_id": "arxiv:2401.00007",
            "title": "Variance Reduction for Agent Training",
            "url": "https://arxiv.org/abs/2401.00007",
            "source": "arxiv",
            "tags": ["arxiv"],
            "reading_depth": "abstract",
            "abstract": (
                "Agent training has high gradient variance in long-horizon tasks. "
                "We propose a control-variate estimator for policy gradients. "
                "Results show that the estimator improves sample efficiency by 20 percent."
            ),
        }

    def test_abstract_extract(self) -> None:
        preview = summarize_abstract(self.record)
        self.assertIn("high gradient variance", preview["problem"])
        self.assertIn("control-variate estimator", preview["approach"])
        self.assertIn("improves sample efficiency", preview["evidence"])

    def test_missing_abstract(self) -> None:
        preview = summarize_abstract({})
        self.assertIn("not yet been completed", preview["problem"])
        self.assertIn("Do not use", preview["limitations"])

    def test_reading_depth(self) -> None:
        reading = {
            "stable_id": self.record["stable_id"],
            "reading_depth": "full_text",
        }
        paper = compact_paper(
            self.record,
            reading,
        )
        self.assertEqual(paper["reading_depth"], "full_text")
        self.assertNotIn("full_reading", paper)
        self.assertEqual(
            paper["full_reading_path"],
            reading_public_path(self.record["stable_id"], reading),
        )
        self.assertIn("variance-control", [item["id"] for item in paper["tricks"]])

    def test_verified_depth(self) -> None:
        paper = compact_paper(
            self.record,
            {"stable_id": self.record["stable_id"], "reading_depth": "verified"},
        )
        self.assertEqual(paper["reading_depth"], "verified")
        self.assertIn("full_reading_path", paper)

    def test_preview_path(self) -> None:
        paper = compact_paper(self.record)
        self.assertEqual(paper["reading_depth"], "abstract")
        self.assertNotIn("full_reading", paper)
        self.assertNotIn("full_reading_path", paper)

    def test_context_reading(self) -> None:
        record = {
            **self.record,
            "record_kind": "non_paper_context",
            "note": "A curator comment retained for provenance.",
        }
        paper = compact_paper(
            record,
            {"stable_id": record["stable_id"], "reading_depth": "verified"},
        )
        self.assertEqual(paper["reading_depth"], "context")
        self.assertNotIn("full_reading", paper)
        self.assertNotIn("full_reading_path", paper)
        self.assertIn("not a paper", paper["reading"]["problem"])


if __name__ == "__main__":
    unittest.main()
