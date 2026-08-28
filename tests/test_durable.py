from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import merge  # noqa: E402
from archive import read_shard  # noqa: E402
from corpus import check_root, pack_root, unpack_root  # noqa: E402
from harvest import run_harvest  # noqa: E402
from events import LEDGER_NAME, MERGE_NAME  # noqa: E402
from oai import Page  # noqa: E402
from rank import load_rules  # noqa: E402


RULES = load_rules(ROOT / "data/source/feed.json")


class FakeClient:
    def __init__(self, page: Page) -> None:
        self.page = page

    def pages(self, start=None, end=None, token=None):
        yield self.page


def paper(identifier: str, *, month: str = "08", stamp: str = "2026-08-20"):
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A durable corpus study",
        "abstract": "We test controlled learning evidence.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": f"2026-{month}-01",
        "updated": "2026-08-10",
        "datestamp": stamp,
        "deleted": False,
    }


def tombstone(identifier: str, stamp: str) -> dict:
    return {"id": identifier, "datestamp": stamp, "deleted": True}


def seal(root: Path, generation: str, records: tuple[dict, ...]) -> None:
    page = Page(
        records=records,
        token=None,
        response_date="2026-08-26T20:00:00Z",
    )
    run_harvest(root, generation, FakeClient(page))


class DurableTests(unittest.TestCase):
    def test_redacted_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            record = paper("2608.00001")
            record["title"] = "contact@university.edu"

            seal(root, "redacted", (record,))
            manifest = merge.merge_generation(root, "redacted", archive, RULES)
            saved = read_shard(archive / "2026-08.json.gz")["papers"]

            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(saved[0]["title"], "arXiv 2608.00001")

    def test_move_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            identifier = "2608.00001"
            seal(root, "first", (paper(identifier),))
            merge.merge_generation(root, "first", archive, RULES)
            seal(root, "move", (paper(identifier, month="07", stamp="2026-08-21"),))
            original = merge.merge_month

            def fail_month(*args, **kwargs):
                changed = original(*args, **kwargs)
                if args[1] == "2026-07":
                    raise RuntimeError("simulated shard interruption")
                return changed

            with (
                patch.object(merge, "merge_month", side_effect=fail_month),
                self.assertRaisesRegex(RuntimeError, "interruption"),
            ):
                merge.merge_generation(root, "move", archive, RULES)

            self.assertTrue((archive / MERGE_NAME).is_file())
            with self.assertRaisesRegex(ValueError, "merge is incomplete"):
                check_root(root)
            manifest = merge.merge_generation(root, "move", archive, RULES)

            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(
                [
                    row["id"]
                    for row in read_shard(archive / "2026-07.json.gz")["papers"]
                ],
                [identifier],
            )
            self.assertEqual(read_shard(archive / "2026-08.json.gz")["papers"], [])
            self.assertFalse((archive / MERGE_NAME).exists())
            check_root(root)

    def test_first_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            seal(root, "first", (paper("2608.00001"),))
            with (
                patch.object(
                    merge, "save_events", side_effect=RuntimeError("ledger stop")
                ),
                self.assertRaisesRegex(RuntimeError, "ledger stop"),
            ):
                merge.merge_generation(root, "first", archive, RULES)

            self.assertTrue((archive / MERGE_NAME).is_file())
            manifest = merge.merge_generation(root, "first", archive, RULES)
            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertFalse((archive / MERGE_NAME).exists())
            check_root(root)

    def test_ledger_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            identifier = "2608.00001"
            seal(root, "current", (paper(identifier, stamp="2026-08-21"),))
            merge.merge_generation(root, "current", archive, RULES)
            (archive / LEDGER_NAME).unlink()

            with self.assertRaisesRegex(ValueError, "ledger is missing"):
                check_root(root)
            seal(root, "stale", (tombstone(identifier, "2026-08-15"),))
            with self.assertRaisesRegex(ValueError, "ledger is missing"):
                merge.merge_generation(root, "stale", archive, RULES)
            self.assertEqual(
                read_shard(archive / "2026-08.json.gz")["papers"][0]["id"],
                identifier,
            )

    def test_empty_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            identifier = "2608.00001"
            seal(root, "deleted", (tombstone(identifier, "2026-08-21"),))
            manifest = merge.merge_generation(root, "deleted", archive, RULES)
            self.assertEqual(manifest["counts"]["all"], 0)
            (archive / LEDGER_NAME).unlink()

            with self.assertRaisesRegex(ValueError, "ledger is missing"):
                check_root(root)
            seal(root, "stale", (paper(identifier, stamp="2026-08-15"),))
            with self.assertRaisesRegex(ValueError, "ledger is missing"):
                merge.merge_generation(root, "stale", archive, RULES)

    def test_ledger_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            seal(root, "first", (paper("2608.00001"),))
            merge.merge_generation(root, "first", archive, RULES)
            with sqlite3.connect(archive / LEDGER_NAME) as database:
                database.execute("UPDATE events SET month='2026-07'")

            with self.assertRaisesRegex(ValueError, "disagrees"):
                check_root(root)

    def test_ledger_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            seal(root, "first", (paper("2608.00001"),))
            merge.merge_generation(root, "first", archive, RULES)
            with sqlite3.connect(archive / LEDGER_NAME) as database:
                database.execute("CREATE TABLE private_data (value TEXT)")

            with self.assertRaisesRegex(ValueError, "schema"):
                check_root(root)

    def test_pack_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "corpus"
            archive = root / "archive"
            bundle = base / "corpus.tar.gz"
            restored = base / "restored"
            seal(root, "first", (paper("2608.00001"),))
            merge.merge_generation(root, "first", archive, RULES)
            ledger = archive / LEDGER_NAME
            digest = hashlib.sha256(ledger.read_bytes()).hexdigest()

            pack_root(root, bundle)
            unpack_root(bundle, restored)

            saved = restored / "archive" / LEDGER_NAME
            self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), digest)
            check_root(restored)


if __name__ == "__main__":
    unittest.main()
