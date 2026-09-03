from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import write_manifest, write_shard  # noqa: E402
from catalog import build_catalog, catalog_text, check_catalog  # noqa: E402


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(identifier: str, year: int, author: str) -> dict:
    published = f"{year}-01-02T00:00:00Z"
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A sparse routing algorithm for learning systems",
        "abstract": "We propose a sparse routing algorithm for controlled agents.",
        "authors": [author],
        "categories": ["cs.LG", "stat.ML"],
        "primary_category": "cs.LG",
        "published": published,
        "updated": published,
        "scope": "likely",
        "relevance": {},
        "interest": {},
        "topics": [route("agents")],
        "tricks": [route("routing-and-moe")],
    }


def shard(year: int, papers: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "policy_version": "catalog-test-1",
        "month": f"{year}-01",
        "days": [],
        "counts": {
            "all": len(papers),
            "likely": len(papers),
            "possible": 0,
            "outside": 0,
        },
        "papers": papers,
    }


class CatalogTests(unittest.TestCase):
    def test_workflow_catalog(self) -> None:
        workflow = (ROOT / ".github/workflows/catalog.yml").read_text(encoding="utf-8")
        for text in (
            "contents: write",
            'default: "corpus-v2"',
            "pipeline/catalog.py",
            "tests.test_catalog",
            "web/public/data/catalog.json",
            'git add "$CATALOG_OUTPUT"',
            "Main changed during catalog generation",
            "gh workflow run check.yml --ref main",
        ):
            with self.subTest(text=text):
                self.assertIn(text, workflow)
        for text in ("git add data/cache", "git add $ARCHIVE_ROOT", "force: true"):
            with self.subTest(text=text):
                self.assertNotIn(text, workflow)

    def build(self, *, two_years: bool = True) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = [
                paper(f"2301.{index:05d}", 2023, f"Author {index % 3}")
                for index in range(1, 7)
            ]
            write_shard(root, shard(2023, first))
            if two_years:
                second = [
                    paper(f"2401.{index:05d}", 2024, f"Author {index % 4}")
                    for index in range(1, 7)
                ]
                write_shard(root, shard(2024, second))
            write_manifest(root)
            return build_catalog(root)

    def test_counts_candidates(self) -> None:
        value = self.build()

        self.assertIs(check_catalog(value), value)
        self.assertEqual(value["corpus"]["source_count"], 12)
        self.assertEqual(value["coverage"]["eligible_direction_papers"], 12)
        self.assertEqual(value["counts"]["arxiv_subjects"], 2)
        self.assertEqual(value["counts"]["candidate_directions"], 2)
        self.assertEqual(value["counts"]["eligible_directions"], 2)
        self.assertEqual(
            {row["paper_count"] for row in value["subjects"]},
            {12},
        )
        self.assertEqual(
            next(row for row in value["areas"] if row["id"] == "agents")[
                "all_paper_count"
            ],
            12,
        )
        for row in value["directions"]:
            self.assertEqual(row["support_count"], 12)
            self.assertEqual(row["year_count"], 2)
            self.assertEqual(row["independent_author_groups_at_least"], 3)
            self.assertEqual(len(row["support_ids"]), 6)

    def test_year_evidence(self) -> None:
        value = self.build(two_years=False)

        self.assertEqual(value["counts"]["eligible_directions"], 0)
        self.assertEqual(value["directions"], [])

    def test_rejects_tampering(self) -> None:
        value = self.build()
        changed = copy.deepcopy(value)
        changed["directions"][0]["status"] = "reviewed"
        with self.assertRaisesRegex(ValueError, "candidate direction"):
            check_catalog(changed)

        changed = copy.deepcopy(value)
        changed["coverage"]["scanned_papers"] += 1
        with self.assertRaisesRegex(ValueError, "coverage"):
            check_catalog(changed)

    def test_is_deterministic(self) -> None:
        self.assertEqual(self.build(), self.build())

    def test_json_format(self) -> None:
        self.assertIn('"tiny": 1e-6', catalog_text({"tiny": 1e-6}))
        self.assertNotIn("e-0", catalog_text({"tiny": 1e-6}))


if __name__ == "__main__":
    unittest.main()
