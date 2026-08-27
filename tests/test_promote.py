from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from promote import ID_OFFSET, base_records, build_corpus, corpus_id  # noqa: E402


def feed_paper(identifier: str, *, updated: str = "2026-08-21") -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": f"Learning paper {identifier}",
        "abstract": "We study machine learning.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2026-08-21",
        "updated": updated,
        "comment": "",
        "relevance": {"relevant": True, "score": 8.0},
        "interest": {"score": 4.0},
    }


def base_record(identifier: int, stable_id: str) -> dict:
    return {"id": identifier, "stable_id": stable_id, "title": stable_id}


class PromoteTests(unittest.TestCase):
    def test_corpus_id(self) -> None:
        self.assertEqual(corpus_id("2608.00001"), ID_OFFSET + 26_080_0001)
        self.assertEqual(corpus_id("2608.12345"), ID_OFFSET + 26_081_2345)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            corpus_id("cs/0601001")

    def test_base_rows(self) -> None:
        source = [{"id": 2}, {"id": 1}]
        enriched = [base_record(1, "arxiv:one"), base_record(2, "arxiv:two")]
        enriched[0]["comment"] = "Contact author@example.edu"

        rows = base_records(source, enriched)

        self.assertEqual([row["id"] for row in rows], [2, 1])
        self.assertEqual(rows[1]["comment"], "")

    def test_base_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing 1"):
            base_records([{"id": 1}], [])

    def test_promotes_all(self) -> None:
        base = [base_record(1, "arxiv:2608.00001")]
        days = [
            {
                "date": "2026-08-21",
                "papers": [feed_paper("2608.00001"), feed_paper("2608.00003")],
            },
            {
                "date": "2026-08-22",
                "papers": [feed_paper("2608.00002")],
            },
        ]

        corpus, report = build_corpus(base, days)

        self.assertEqual(
            [row["stable_id"] for row in corpus],
            ["arxiv:2608.00001", "arxiv:2608.00002", "arxiv:2608.00003"],
        )
        self.assertEqual(report["input_rows"], 3)
        self.assertEqual(report["base_duplicates"], 1)
        self.assertEqual(report["promoted_count"], 2)
        self.assertEqual(report["corpus_count"], 3)

    def test_repeat_updates(self) -> None:
        days = [
            {
                "date": "2026-08-21",
                "papers": [feed_paper("2608.00001", updated="2026-08-21")],
            },
            {
                "date": "2026-08-22",
                "papers": [feed_paper("2608.00001", updated="2026-08-22")],
            },
        ]

        corpus, report = build_corpus([], days)

        self.assertEqual(len(corpus), 1)
        self.assertEqual(corpus[0]["updated"], "2026-08-22")
        self.assertEqual(report["repeat_rows"], 1)


if __name__ == "__main__":
    unittest.main()
