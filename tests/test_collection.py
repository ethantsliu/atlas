from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from collection import public_collection, validate_collection, validate_row  # noqa: E402


def sample_row(identifier: int = 1) -> dict:
    return {
        "id": identifier,
        "title": "A paper",
        "url": "https://papers.example.org/paper.pdf",
        "section": "Research",
        "tags": ["paper"],
        "note": None,
        "source": "collection",
    }


class CollectionTests(unittest.TestCase):
    def test_valid_row(self) -> None:
        self.assertEqual(validate_row(sample_row(), 0), sample_row())

    def test_unsafe_row(self) -> None:
        row = sample_row()
        row["url"] = "file:///tmp/private.pdf"
        with self.assertRaisesRegex(RuntimeError, "unsafe URL"):
            validate_row(row, 0)

        row = sample_row()
        row["hidden"] = "unexpected"
        with self.assertRaisesRegex(RuntimeError, "field set"):
            validate_row(row, 0)

    def test_duplicate_rows(self) -> None:
        rows = [sample_row(index + 1) for index in range(2000)]
        rows[-1]["id"] = rows[0]["id"]
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            validate_collection(rows)

    def test_private_context(self) -> None:
        rows = [
            sample_row(identifier)
            for identifier in (1, 2092, 2110, 2111, 2112, 2125, 2170)
        ]
        rows[0]["note"] = "Private curator annotation"

        public = public_collection(rows)

        self.assertEqual([row["id"] for row in public], [1])
        self.assertEqual(set(public[0]), {"id", "title", "url", "source"})

    def test_title_boundary(self) -> None:
        annotated = sample_row(1)
        annotated["title"] = "READ THIS! ALSO LINK TO: A Paper"
        linked = sample_row(2)
        linked["title"] = "https://papers.example.org/paper.pdf"

        public = public_collection([annotated, linked], {"1": "A Canonical Paper"})

        self.assertEqual(
            public,
            [
                {
                    "id": 1,
                    "title": "A Canonical Paper",
                    "url": annotated["url"],
                    "source": "collection",
                }
            ],
        )

    def test_alias_filter(self) -> None:
        rows = [sample_row(1), sample_row(882), sample_row(2169)]

        self.assertEqual([row["id"] for row in public_collection(rows)], [1])


if __name__ == "__main__":
    unittest.main()
