import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from archive import (
    add_day,
    build_month,
    merge_month,
    read_manifest,
    scope_paper,
    shard_bytes,
)
from archivecheck import validate_archive
from backfill import completed_days, harvest_days, pending_days
from rank import load_rules


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")


def paper(identifier: str, **changes) -> dict:
    value = {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A geometric theorem",
        "abstract": "We prove a result in topology.",
        "authors": ["Ada Researcher"],
        "categories": ["math.AT"],
        "primary_category": "math.AT",
        "published": "2020-01-02T01:00:00Z",
        "updated": "2020-01-02T01:00:00Z",
        "comment": "",
    }
    return {**value, **changes}


def intake(papers: list[dict]) -> dict:
    return {
        "source_total": len(papers),
        "fetched_count": len(papers),
        "unique_count": len({item["id"] for item in papers}),
        "page_count": 1,
        "query": "submittedDate:[202001020000 TO 202001022359]",
        "papers": papers,
    }


class ArchiveTests(unittest.TestCase):
    def test_scope_retention(self) -> None:
        likely = scope_paper(
            paper("2001.00001", categories=["cs.LG"]),
            RULES,
        )
        possible = scope_paper(paper("2001.00002"), RULES)
        outside = scope_paper(
            paper("2001.00003", categories=["physics.optics"]),
            RULES,
        )

        self.assertEqual(likely["scope"], "likely")
        self.assertEqual(possible["scope"], "possible")
        self.assertEqual(outside["scope"], "outside")

    def test_month_complete(self) -> None:
        payload = build_month(
            date(2020, 1, 2),
            intake([paper("2001.00001"), paper("2001.00002")]),
            RULES,
        )

        self.assertEqual(payload["counts"]["all"], 2)
        self.assertEqual(
            sum(payload["counts"][key] for key in ("likely", "possible", "outside")), 2
        )
        self.assertEqual(len(payload["papers"]), 2)

    def test_merge_updates(self) -> None:
        prior = build_month(date(2020, 1, 2), intake([paper("2001.00001")]), RULES)
        current = build_month(
            date(2020, 1, 3),
            intake(
                [
                    paper(
                        "2001.00001",
                        title="Updated title",
                        published="2020-01-03T01:00:00Z",
                        updated="2020-01-03T02:00:00Z",
                    )
                ]
            ),
            RULES,
        )

        merged = merge_month(prior, current)

        self.assertEqual(len(merged["days"]), 2)
        self.assertEqual(len(merged["papers"]), 1)
        self.assertEqual(merged["papers"][0]["title"], "Updated title")

    def test_stable_bytes(self) -> None:
        payload = build_month(date(2020, 1, 2), intake([paper("2001.00001")]), RULES)

        left = shard_bytes(payload)
        right = shard_bytes(json.loads(gzip.decompress(left)))

        self.assertEqual(left, right)

    def test_day_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = add_day(
                root,
                date(2020, 1, 2),
                intake([paper("2001.00001")]),
                RULES,
            )
            manifest = add_day(
                root,
                date(2020, 1, 2),
                intake([paper("2001.00001")]),
                RULES,
            )

            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(manifest["shards"][0]["days"], 1)
            self.assertEqual(manifest["shards"][0]["dates"], ["2020-01-02"])

    def test_remote_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "shards": [
                            {
                                "month": "2020-01",
                                "dates": ["2020-01-01", "2020-01-02"],
                                "counts": {
                                    "all": 2,
                                    "likely": 1,
                                    "possible": 0,
                                    "outside": 1,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(completed_days(root), {"2020-01-01", "2020-01-02"})
            self.assertEqual(len(read_manifest(root)["shards"]), 1)

    def test_archive_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = add_day(
                root,
                date(2020, 1, 2),
                intake([paper("2001.00001")]),
                RULES,
            )

            self.assertEqual(validate_archive(root), manifest)

            manifest["counts"]["all"] = 2
            (root / "index.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "global counts"):
                validate_archive(root)

    def test_pending_days(self) -> None:
        pending = pending_days(
            date(2020, 1, 1),
            date(2020, 1, 5),
            {"2020-01-01", "2020-01-03"},
            2,
        )

        self.assertEqual(pending, [date(2020, 1, 5), date(2020, 1, 2)])

    def test_transient_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def fetcher(day, size, delay):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise HTTPError("https://export.arxiv.org", 429, "busy", {}, None)
                return intake([paper("2001.00001")])

            completed, deferred = harvest_days(
                [date(2020, 1, 2), date(2020, 1, 3)],
                root,
                RULES,
                500,
                0,
                fetcher,
            )

            self.assertEqual(completed, 1)
            self.assertEqual(deferred, "HTTP 429")
            self.assertEqual(read_manifest(root)["counts"]["all"], 1)


if __name__ == "__main__":
    unittest.main()
