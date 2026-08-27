from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from identifiers import canonical_id  # noqa: E402


class GeneratedDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.atlas = json.loads((ROOT / "data/generated/atlas.json").read_text())
        cls.manifest = json.loads(
            (ROOT / "data/generated/corpus_manifest.json").read_text()
        )
        cls.source_papers = json.loads((ROOT / "data/source/papers.json").read_text())
        cls.promotion = json.loads((ROOT / "data/generated/promotion.json").read_text())
        cls.overrides = json.loads((ROOT / "data/source/overrides.json").read_text())

    def test_collection_counts(self) -> None:
        self.assertEqual(self.manifest["paper_count"], 2185)
        self.assertEqual(
            len(self.atlas["papers"]),
            self.manifest["paper_count"] + self.promotion["promoted_count"],
        )
        self.assertEqual(self.atlas["meta"]["paper_count"], len(self.atlas["papers"]))
        self.assertEqual(self.manifest["excluded_private_context"], 6)
        self.assertEqual(self.manifest["excluded_duplicate_papers"], 17)
        self.assertEqual(self.atlas["meta"]["context_entry_count"], 0)
        self.assertTrue(
            all(
                set(row) == {"id", "title", "url", "source"}
                for row in self.source_papers
            )
        )
        self.assertTrue(
            all(
                not {"note", "section", "tags"}.intersection(row)
                for row in self.atlas["papers"]
            )
        )

    def test_manifest_count(self) -> None:
        canonical_ids = {
            canonical_id(paper, self.overrides.get(str(paper["id"])))[0]
            for paper in self.source_papers
        }
        self.assertEqual(len(canonical_ids), self.manifest["unique_canonical_records"])
        stable_ids = [paper["stable_id"] for paper in self.atlas["papers"]]
        self.assertEqual(len(stable_ids), len(set(stable_ids)))
        self.assertTrue(
            all(
                override.get("source_override_reason")
                for override in self.overrides.values()
            )
        )

    def test_idea_feasibility(self) -> None:
        for idea in self.atlas["ideas"]:
            with self.subTest(idea=idea["id"]):
                feasibility = idea["feasibility"]
                self.assertEqual(feasibility["score"], round(feasibility["score"], 1))
                self.assertEqual(len(feasibility["factors"]), 5)

    def test_score_lexeme(self) -> None:
        paths = (
            ROOT / "data/source/flagships.json",
            ROOT / "data/generated/atlas.json",
            ROOT / "web/public/data/atlas.json",
        )
        for path in paths:
            payload = json.loads(
                path.read_text(),
                parse_float=Decimal,
                parse_int=Decimal,
            )
            ideas = payload if isinstance(payload, list) else payload["ideas"]
            for idea in ideas:
                with self.subTest(path=path, idea=idea["id"]):
                    score = idea["feasibility"]["score"]
                    self.assertIsInstance(score, Decimal)
                    self.assertEqual(score.as_tuple().exponent, -1)

    def test_reading_competitors(self) -> None:
        full_readings = [
            paper
            for paper in self.atlas["papers"]
            if paper["reading_depth"] in {"full_text", "verified"}
        ]
        self.assertGreater(len(full_readings), 0)
        for paper in full_readings:
            with self.subTest(paper=paper["stable_id"]):
                self.assertNotIn("full_reading", paper)
                detail_path = (
                    ROOT / "web/public" / paper["full_reading_path"].lstrip("/")
                )
                reading = json.loads(detail_path.read_text(encoding="utf-8"))
                self.assertEqual(reading["stable_id"], paper["stable_id"])
                self.assertEqual(reading["reading_depth"], paper["reading_depth"])
                self.assertGreaterEqual(len(reading["competitive_landscape"]), 3)
                self.assertTrue(reading["novelty_assessment"])

    def test_screening_label(self) -> None:
        for idea in self.atlas["ideas"]:
            if idea["brief"]["status"] == "provisional":
                with self.subTest(idea=idea["id"]):
                    self.assertTrue(idea["feasibility"]["screening_estimate"])
                    self.assertLessEqual(idea["feasibility"]["score"], 7.0)


if __name__ == "__main__":
    unittest.main()
