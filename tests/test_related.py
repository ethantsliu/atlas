from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from related import build_work_rows  # noqa: E402


def paper(
    collection_id: int,
    stable_id: str,
    title: str,
    abstract: str = "",
) -> dict:
    return {
        "id": collection_id,
        "stable_id": stable_id,
        "title": title,
        "abstract": abstract,
        "categories": ["cs.LG"],
        "url": f"https://arxiv.org/abs/{stable_id.removeprefix('arxiv:')}",
    }


class RelatedWorkRowTests(unittest.TestCase):
    def test_lexical_candidate(self) -> None:
        records = [
            paper(1, "arxiv:1", "Rarebridge optimization"),
            paper(2, "arxiv:2", "Rarebridge search"),
            paper(3, "arxiv:3", "Unrelated photon geometry"),
        ]

        rows = build_work_rows(records, {})

        self.assertEqual(rows[0]["candidates"][0]["stable_id"], "arxiv:2")
        self.assertEqual(rows[0]["candidates"][0]["status"], "candidate_only")
        self.assertIn("rarebridge", rows[0]["candidates"][0]["shared_terms"])
        self.assertEqual(rows[0]["review_status"], "unreviewed")

    def test_context_route(self) -> None:
        record = {
            **paper(1, "urlhash:context", "Workshop index"),
            "record_kind": "non_paper_context",
        }

        row = build_work_rows([record], {})[0]

        self.assertEqual(row["review_status"], "not_applicable")
        self.assertEqual(row["candidates"], [])
        self.assertEqual(row["reviewed_competitors"], [])

    def test_duplicate_exclusion(self) -> None:
        records = [
            paper(1, "arxiv:1", "Rarebridge optimization"),
            paper(2, "arxiv:1", "Rarebridge optimization duplicate"),
            paper(3, "arxiv:2", "Rarebridge search"),
        ]

        rows = build_work_rows(records, {})

        for row in rows:
            self.assertTrue(
                all(
                    candidate["stable_id"] != row["stable_id"]
                    for candidate in row["candidates"]
                )
            )
        self.assertEqual(
            [candidate["stable_id"] for candidate in rows[0]["candidates"]],
            ["arxiv:2"],
        )

    def test_competitor_copy(self) -> None:
        competitors = [
            {
                "canonical_id": "arxiv:prior",
                "title": "Prior work",
                "url": "https://arxiv.org/abs/prior",
                "relationship": "prior",
                "difference": "A direct methodological difference.",
            }
        ]
        readings = {
            "arxiv:1": {
                "stable_id": "arxiv:1",
                "competitive_landscape": competitors,
            }
        }

        row = build_work_rows([paper(1, "arxiv:1", "Rarebridge")], readings)[0]

        self.assertEqual(row["review_status"], "reviewed")
        self.assertEqual(row["reviewed_competitors"], competitors)
        self.assertIsNot(row["reviewed_competitors"], competitors)
        self.assertIsNot(row["reviewed_competitors"][0], competitors[0])


if __name__ == "__main__":
    unittest.main()
