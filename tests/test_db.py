import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from db import (
    corpus_rows,
    corpus_text,
    day_values,
    paper_values,
    prune_days,
    search_text,
    sync_corpus,
    sync_days,
)
from sync import load_corpus, load_days, trim_days

ROOT = Path(__file__).resolve().parents[1]
FEED_ROOT = ROOT / "data/generated/feed"


class FakeCursor:
    def __init__(self, result=None) -> None:
        self.calls = []
        self.batches = []
        self.result = result

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql, values=None) -> None:
        self.calls.append((sql, values))

    def executemany(self, sql, values) -> None:
        self.batches.append((sql, values))

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, result=None) -> None:
        self.value = FakeCursor(result)

    def cursor(self) -> FakeCursor:
        return self.value


def load_sample() -> dict:
    return json.loads((FEED_ROOT / "2026-08-21.json").read_text(encoding="utf-8"))


class DatabaseTests(unittest.TestCase):
    def test_day_values(self) -> None:
        payload = load_sample()
        values = day_values(payload)

        self.assertEqual(values[0], "2026-08-21")
        self.assertEqual(values[4], 734)
        self.assertEqual(values[8], 276)
        self.assertTrue(values[-1])

    def test_paper_values(self) -> None:
        payload = load_sample()
        rows = paper_values(payload)

        self.assertEqual(len(rows), 276)
        self.assertEqual(rows[0][1], payload["shortlist_ids"][0])
        self.assertTrue(rows[0][3])
        self.assertFalse(rows[-1][3])
        self.assertEqual(json.loads(rows[0][20]), payload["papers"][0]["topics"])

    def test_search_text(self) -> None:
        paper = load_sample()["papers"][0]
        text = search_text(paper)

        self.assertIn(paper["title"], text)
        self.assertIn("agents", text)
        self.assertIn("self-play", text)

    def test_rejects_partial(self) -> None:
        payload = load_sample()
        payload["source"]["complete"] = False

        with self.assertRaisesRegex(ValueError, "complete source day"):
            day_values(payload)

    def test_prune_cutoff(self) -> None:
        cursor = FakeCursor()
        cutoff = prune_days(cursor, date(2026, 8, 21), 365)

        self.assertEqual(cutoff, date(2025, 8, 22))
        self.assertEqual(cursor.calls[-1][1], (cutoff,))

    def test_atomic_sync(self) -> None:
        connection = FakeConnection()
        payload = load_sample()

        count, cutoff = sync_days(connection, [payload], 365)

        self.assertEqual(count, 276)
        self.assertEqual(cutoff, date(2025, 8, 22))
        self.assertEqual(len(connection.value.batches[0][1]), 276)

    def test_load_days(self) -> None:
        payloads = load_days(FEED_ROOT, "2026-08-21")

        self.assertEqual([item["date"] for item in payloads], ["2026-08-21"])

    def test_rejects_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            load_days(FEED_ROOT, "../../secret")

    def test_trim_days(self) -> None:
        payload = load_sample()
        prior = {**payload, "date": "2025-01-01"}

        self.assertEqual(trim_days([prior, payload], 180), [payload])

    def test_corpus_rows(self) -> None:
        atlas, enriched, _digest = load_corpus()
        rows = corpus_rows(atlas, enriched)

        self.assertEqual(len(rows), 2205)
        self.assertEqual(rows[0][0], atlas["papers"][0]["id"])
        self.assertEqual(rows[0][2], atlas["papers"][0]["collection_id"])
        self.assertIn("continual", rows[0][-1].lower())

    def test_corpus_text(self) -> None:
        atlas, enriched, _digest = load_corpus()
        details = {paper["id"]: paper for paper in enriched}
        paper = atlas["papers"][0]

        text = corpus_text(paper, details[paper["collection_id"]])

        self.assertIn(paper["title"], text)
        self.assertIn(paper["topics"][0]["id"], text)

    def test_corpus_sync(self) -> None:
        atlas, enriched, digest = load_corpus()
        connection = FakeConnection()

        count = sync_corpus(connection, atlas, enriched, digest)

        self.assertEqual(count, 2205)
        self.assertIn("delete from public.corpus_papers", connection.value.calls[1][0])
        self.assertEqual(len(connection.value.batches[0][1]), 2205)

    def test_corpus_rejects(self) -> None:
        atlas, enriched, _digest = load_corpus()
        atlas["papers"] = atlas["papers"][:-1]

        with self.assertRaisesRegex(ValueError, "count or paper identity"):
            corpus_rows(atlas, enriched)

    def test_corpus_skip(self) -> None:
        atlas, enriched, digest = load_corpus()
        connection = FakeConnection((digest,))

        count = sync_corpus(connection, atlas, enriched, digest)

        self.assertEqual(count, 0)
        self.assertEqual(len(connection.value.calls), 1)
        self.assertEqual(connection.value.batches, [])


if __name__ == "__main__":
    unittest.main()
