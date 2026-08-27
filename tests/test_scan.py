from __future__ import annotations

import copy
import hashlib
import os
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import write_manifest, write_shard  # noqa: E402
from scan import scan_archive  # noqa: E402
from synth import make_manifest  # noqa: E402


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(identifier: str, title: str = "A sparse routing algorithm") -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": title,
        "abstract": "We propose a sparse routing algorithm for controlled agents.",
        "authors": ["Public Author"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2024-01-02T00:00:00Z",
        "updated": "2024-01-02T00:00:00Z",
        "scope": "likely",
        "relevance": {},
        "interest": {},
        "topics": [route("agents")],
        "tricks": [route("routing-and-moe")],
    }


def shard(papers: list[dict], month: str = "2024-01") -> dict:
    return {
        "schema_version": 1,
        "policy_version": "fixture-1",
        "month": month,
        "days": [],
        "counts": {
            "all": len(papers),
            "likely": len(papers),
            "possible": 0,
            "outside": 0,
        },
        "papers": papers,
    }


def setup(root: Path, papers: list[dict]) -> tuple[dict, dict]:
    write_shard(root, shard(papers))
    manifest = write_manifest(root)
    sources = [
        {"source_id": f"arxiv:{row['month']}", "sha256": row["sha256"]}
        for row in manifest["shards"]
    ]
    return manifest, make_manifest("scan-test-1", sources)


class ScanTests(unittest.TestCase):
    def test_stream(self) -> None:
        papers = [paper(f"2401.{index:05d}") for index in range(1, 21)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, corpus = setup(root, papers)
            result = scan_archive(root, manifest, corpus, limit=4)

        self.assertEqual(result["loaded_papers"], 20)
        self.assertEqual(result["loaded_months"], ["2024-01"])
        self.assertEqual(len(result["candidates"]), 1)
        idea = result["candidates"][0]
        self.assertEqual(
            idea["support_ids"],
            [f"arxiv:2401.{index:05d}" for index in range(1, 7)],
        )
        self.assertEqual(len(result["trick_candidates"]), 2)
        self.assertTrue(
            all(len(row["sources"]) <= 12 for row in result["trick_candidates"])
        )
        self.assertTrue(
            all(row["support_count"] == 20 for row in result["trick_candidates"])
        )
        related = result["related_work"][idea["candidate_id"]]
        self.assertTrue(
            set(idea["support_ids"]).isdisjoint(
                row["canonical_id"] for row in related["candidates"]
            )
        )
        self.assertEqual(
            related["retrieval_corpus_digest"],
            corpus["corpus_digest"],
        )

    def test_repeat(self) -> None:
        papers = [paper(f"2401.{index:05d}") for index in range(1, 5)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, corpus = setup(root, papers)
            first = scan_archive(root, manifest, corpus, limit=2)
            second = scan_archive(root, copy.deepcopy(manifest), corpus, limit=2)

        self.assertEqual(first, second)

    def test_missing(self) -> None:
        papers = [paper("2401.00001"), paper("2401.00002")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, corpus = setup(root, papers)
            (root / manifest["shards"][0]["path"]).unlink()
            result = scan_archive(root, manifest, corpus, limit=2)

        self.assertEqual(result["loaded_papers"], 0)
        self.assertEqual(result["loaded_months"], [])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["related_work"], {})

    def test_duplicate(self) -> None:
        first = paper("2401.00001")
        second = {
            **paper("2401.00001"),
            "published": "2024-02-02T00:00:00Z",
            "updated": "2024-02-02T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = write_shard(root, shard([first]))
            second_path = write_shard(root, shard([second], "2024-02"))
            first_hash = hashlib.sha256(first_path.read_bytes()).hexdigest()
            second_hash = hashlib.sha256(second_path.read_bytes()).hexdigest()
            manifest = {
                "schema_version": 1,
                "shards": [
                    {
                        "month": "2024-01",
                        "path": first_path.name,
                        "sha256": first_hash,
                    },
                    {
                        "month": "2024-02",
                        "path": second_path.name,
                        "sha256": second_hash,
                    },
                ],
            }
            corpus = make_manifest(
                "scan-test-1",
                [
                    {"source_id": "arxiv:2024-01", "sha256": first_hash},
                    {"source_id": "arxiv:2024-02", "sha256": second_hash},
                ],
            )
            with self.assertRaisesRegex(ValueError, "duplicated"):
                scan_archive(root, manifest, corpus, limit=2)

    def test_archive_dup(self) -> None:
        papers = [paper("2401.00001"), paper("2401.00001")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard(papers))
            with self.assertRaisesRegex(ValueError, "duplicated|papers are invalid"):
                write_manifest(root)

    def test_limits(self) -> None:
        papers = [paper("2401.00001"), paper("2401.00002")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, corpus = setup(root, papers)
            with self.assertRaisesRegex(ValueError, "between 1 and 48"):
                scan_archive(root, manifest, corpus, limit=49)

    @unittest.skipUnless(os.getenv("ATLAS_SCALE_TEST") == "1", "opt-in scale test")
    def test_scale(self) -> None:
        papers = []
        for index in range(100_000):
            prefix = 2001 + index // 10_000
            item = paper(f"{prefix:04d}.{index % 10_000:04d}", "Public corpus study")
            item["abstract"] = "A public abstract for indexing."
            item["topics"] = []
            item["tricks"] = []
            papers.append(item)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, corpus = setup(root, papers)
            del papers
            tracemalloc.start()
            result = scan_archive(root, manifest, corpus, limit=2)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

        self.assertEqual(result["loaded_papers"], 100_000)
        self.assertLess(peak, 350 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
