from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from arxiv import entry_identifier, merge_record, paper_id  # noqa: E402


class ArxivEnrichmentTests(unittest.TestCase):
    def test_malformed_suffix(self) -> None:
        self.assertEqual(paper_id("https://arxiv.org/pdf/2410.12984t"), "2410.12984")

    def test_legacy_category(self) -> None:
        self.assertEqual(
            entry_identifier("http://arxiv.org/abs/hep-th/9901001v2"),
            "hep-th/9901001",
        )

    def test_resume_merge(self) -> None:
        paper = {
            "id": 1,
            "title": "Current collection title",
            "url": "https://arxiv.org/abs/2401.00001",
            "source": "arxiv",
        }
        prior = {
            **paper,
            "title": "Fetched title",
            "arxiv_id": "2401.00001",
            "abstract": "Cached API abstract",
            "authors": ["A. Author"],
            "reading_depth": "abstract",
            "stable_id": "arxiv:2401.00001",
            "identifier_kind": "arxiv",
            "pdf_url_override": "https://example.org/stale.pdf",
            "source_override_reason": "Deleted decision",
            "unexpected_cache_key": "must not survive",
        }

        resumed = merge_record(paper, {}, prior)

        self.assertEqual(resumed["title"], "Current collection title")
        self.assertEqual(resumed["abstract"], "Cached API abstract")
        self.assertNotIn("pdf_url_override", resumed)
        self.assertNotIn("source_override_reason", resumed)
        self.assertNotIn("unexpected_cache_key", resumed)

        changed = merge_record(
            {**paper, "source": "current-source"},
            {
                "pdf_url_override": "https://example.org/current.pdf",
                "source_override_reason": "Current decision",
            },
            prior,
        )
        self.assertEqual(changed["source"], "current-source")
        self.assertEqual(changed["pdf_url_override"], "https://example.org/current.pdf")


if __name__ == "__main__":
    unittest.main()
