from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import corpus  # noqa: E402
import merge  # noqa: E402
from archive import read_shard  # noqa: E402
from corpus import merge_pending, read_cursor, write_cursor  # noqa: E402
from harvest import run_harvest  # noqa: E402
from oai import Page  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data/source/feed.json"


class FakeClient:
    def __init__(self, page: Page) -> None:
        self.page = page

    def pages(self, start=None, end=None, token=None):
        yield self.page


def paper(identifier: str, title: str, stamp: str) -> dict:
    """Create one complete OAI record for a deterministic batch test."""
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": title,
        "abstract": "We test synthetic data with controlled learning evidence.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2020-01-01",
        "updated": stamp,
        "comment": None,
        "datestamp": stamp,
        "deleted": False,
        "version_dates": [],
    }


def seal(root: Path, generation: str, records: tuple[dict, ...]) -> None:
    """Seal one single-page generation under the harvest contract."""
    page = Page(
        records=records,
        token=None,
        response_date="2026-08-27T00:00:00Z",
    )
    run_harvest(root, generation, FakeClient(page))


def cursor(root: Path, pending: list[str]) -> None:
    """Create a cursor with an ordered set of sealed generations."""
    write_cursor(
        root,
        {
            "schema_version": 1,
            "watermark": "2026-08-27T00:00:00Z",
            "active": None,
            "last_generation": pending[-1],
            "pending": pending,
            "merged": [],
            "history": {
                "next_year": 2022,
                "through_year": 2026,
                "complete": False,
            },
        },
    )


class BatchTests(unittest.TestCase):
    def test_ordered_batch(self) -> None:
        """Later equal-stamp events win without repeated archive traversals."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "corpus"
            archive = root / "archive"
            seal(
                root,
                "history-2020",
                (
                    paper("2001.00001", "Earlier title", "2021-01-01"),
                    paper("2001.00002", "First paper", "2021-01-01"),
                ),
            )
            seal(
                root,
                "history-2021",
                (
                    paper("2001.00001", "Later title", "2021-01-01"),
                    paper("2001.00003", "Second paper", "2021-01-02"),
                ),
            )
            pending = ["history-2020", "history-2021"]
            cursor(root, pending)

            with (
                patch("merge.find_moves", wraps=merge.find_moves) as moves,
                patch("merge.active_routes", wraps=merge.active_routes) as routes,
                patch("merge.check_ledger", wraps=merge.check_ledger) as ledger,
                patch("corpus.write_cursor", wraps=corpus.write_cursor) as writes,
            ):
                result = merge_pending(root, archive, RULES)

            papers = read_shard(archive / "2020-01.json.gz")["papers"]
            saved = {row["id"]: row for row in papers}
            self.assertEqual(saved["2001.00001"]["title"], "Later title")
            self.assertEqual(result["pending"], pending)
            self.assertEqual(read_cursor(root)["merged"], pending)
            self.assertEqual(moves.call_count, 1)
            self.assertEqual(routes.call_count, 0)
            self.assertEqual(ledger.call_count, 2)
            self.assertEqual(writes.call_count, 1)

    def test_atomic_cursor(self) -> None:
        """A failed batch cannot partially advance the merged cursor list."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "corpus"
            pending = ["history-2020", "history-2021"]
            cursor(root, pending)

            with patch("corpus.merge_generations", side_effect=RuntimeError("stopped")):
                with self.assertRaisesRegex(RuntimeError, "stopped"):
                    merge_pending(root, root / "archive", RULES)

            self.assertEqual(read_cursor(root)["merged"], [])


if __name__ == "__main__":
    unittest.main()
