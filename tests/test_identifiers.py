from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from identifiers import canonical_id  # noqa: E402


class CanonicalIdentifierTests(unittest.TestCase):
    def test_modern_arxiv(self) -> None:
        stable_id, kind = canonical_id(
            {"url": "https://arxiv.org/pdf/2401.12345v2", "title": "Example"}
        )
        self.assertEqual(stable_id, "arxiv:2401.12345")
        self.assertEqual(kind, "arxiv")

    def test_openreview_forum(self) -> None:
        stable_id, kind = canonical_id(
            {
                "url": "https://openreview.net/forum?id=AbC_123-x",
                "title": "Example",
            }
        )
        self.assertEqual(stable_id, "openreview:AbC_123-x")
        self.assertEqual(kind, "openreview")

    def test_openreview_punctuation(self) -> None:
        stable_id, kind = canonical_id(
            {
                "url": "https://openreview.net/pdf?id=AbC_123-x)",
                "title": "Example",
            }
        )
        self.assertEqual(stable_id, "openreview:AbC_123-x")
        self.assertEqual(kind, "openreview")

    def test_override_priority(self) -> None:
        record = {"url": "https://arxiv.org/list/cs.LG/recent", "title": "Example"}
        override = {
            "stable_id": "arxiv:2510.08009",
            "identifier_kind": "arxiv",
        }
        self.assertEqual(canonical_id(record, override), ("arxiv:2510.08009", "arxiv"))

    def test_fallback_stable(self) -> None:
        record = {"url": "https://example.com/paper/", "title": "A Paper"}
        first = canonical_id(record)
        second = canonical_id(record)
        self.assertEqual(first, second)
        self.assertTrue(first[0].startswith("urlhash:"))


if __name__ == "__main__":
    unittest.main()
