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
    migrate_archive,
    read_manifest,
    read_shard,
    scope_paper,
    shard_bytes,
    shard_meta,
    write_shard,
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
        self.assertNotIn("comment", payload["papers"][0])

    def test_scholarly_text(self) -> None:
        payload = build_month(
            date(2020, 1, 2),
            intake(
                [
                    paper(
                        "2001.00001",
                        abstract=(
                            "Code is available at "
                            "https://github.com/public-lab/public-paper."
                        ),
                        authors=["Ada Researcher <ada@university.edu>"],
                    )
                ]
            ),
            RULES,
        )

        self.assertIn("github.com", payload["papers"][0]["abstract"])
        self.assertEqual(payload["papers"][0]["authors"], ["Ada Researcher"])

    def test_redacted_title(self) -> None:
        payload = build_month(
            date(2020, 1, 2),
            intake([paper("2001.00001", title="contact@university.edu")]),
            RULES,
        )

        self.assertEqual(payload["papers"][0]["title"], "arXiv 2001.00001")

    def test_public_boundary(self) -> None:
        unsafe = (
            {"id": "private-paper"},
            {"title": "Left\u202eright"},
            {"title": "Not  normalized"},
            {"title": "x" * 4_097},
        )
        for changes in unsafe:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "public paper text"):
                    build_month(
                        date(2020, 1, 2),
                        intake([paper("2001.00001", **changes)]),
                        RULES,
                    )

    def test_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            january = build_month(
                date(2020, 1, 2), intake([paper("2001.00001")]), RULES
            )
            february = build_month(
                date(2020, 2, 2),
                intake(
                    [
                        paper(
                            "2001.00001",
                            published="2020-02-02T01:00:00Z",
                            updated="2020-02-02T01:00:00Z",
                        )
                    ]
                ),
                RULES,
            )
            write_shard(root, january)
            write_shard(root, february)
            rows = [
                shard_meta(root / "2020-01.json.gz"),
                shard_meta(root / "2020-02.json.gz"),
            ]
            (root / "index.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "counts": {
                            "all": 2,
                            "likely": 0,
                            "possible": 2,
                            "outside": 0,
                        },
                        "shards": rows,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicated"):
                validate_archive(root)

    def test_shard_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_month(
                date(2020, 1, 2), intake([paper("2001.00001")]), RULES
            )
            payload["papers"][0]["comment"] = "/Users/alice/private/note"
            payload["papers"][0]["secret"] = "/Users/sample/private/note"
            write_shard(root, payload)

            saved = read_shard(root / "2020-01.json.gz")["papers"][0]
            self.assertNotIn("comment", saved)
            self.assertNotIn("secret", saved)

    def test_exact_shard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_month(
                date(2020, 1, 2), intake([paper("2001.00001")]), RULES
            )
            path = write_shard(root, payload)
            forged = json.loads(gzip.decompress(path.read_bytes()))
            forged["papers"][0]["source_path"] = "/tmp/private.json"
            path.write_bytes(shard_bytes(forged))

            with self.assertRaisesRegex(ValueError, "public paper text"):
                read_shard(path)

    def test_nested_boundary(self) -> None:
        payload = build_month(
            date(2020, 1, 2),
            intake(
                [
                    paper(
                        "2001.00001",
                        title=(
                            "An agent uses retrieval and synthetic data for robust "
                            "evaluation"
                        ),
                        categories=["cs.LG"],
                    )
                ]
            ),
            RULES,
        )
        nested = payload["papers"][0]
        self.assertTrue(nested["topics"])
        self.assertTrue(nested["tricks"])
        attacks = (
            ("relevance", "private_context", "/Users/alice/project"),
            ("interest", "private_context", "local notes"),
            ("relevance", "reasons", ["strong signals: @private_handle"]),
            ("interest", "reasons", ["interest signals: file:///tmp/note"]),
            ("topics", 0, {**nested["topics"][0], "private_context": "secret"}),
            (
                "tricks",
                0,
                {**nested["tricks"][0], "evidence": ["/home/alice/private"]},
            ),
            ("topics", 0, {**nested["topics"][0], "id": "private-project"}),
        )
        for field, key, value in attacks:
            with self.subTest(field=field, key=key):
                forged = json.loads(json.dumps(payload))
                target = forged["papers"][0][field]
                if isinstance(key, int):
                    target[key] = value
                else:
                    target[key] = value
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ValueError, "public paper text"):
                        write_shard(Path(directory), forged)

    def test_nested_scores(self) -> None:
        payload = build_month(
            date(2020, 1, 2),
            intake([paper("2001.00001", categories=["cs.LG"])]),
            RULES,
        )
        attacks = (
            ("relevance", "score", float("nan")),
            ("relevance", "score", True),
            ("interest", "score", 10.01),
        )
        for field, key, value in attacks:
            with self.subTest(field=field, key=key, value=value):
                forged = json.loads(json.dumps(payload))
                forged["papers"][0][field][key] = value
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ValueError, "public paper text"):
                        write_shard(Path(directory), forged)

    def test_nested_shard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_month(
                date(2020, 1, 2),
                intake([paper("2001.00001", categories=["cs.LG"])]),
                RULES,
            )
            path = write_shard(root, payload)
            forged = json.loads(gzip.decompress(path.read_bytes()))
            forged["papers"][0]["relevance"]["private_context"] = "/Users/alice/project"
            path.write_bytes(shard_bytes(forged))

            with self.assertRaisesRegex(ValueError, "public paper text"):
                read_shard(path)

    def test_exact_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_month(
                date(2020, 1, 2), intake([paper("2001.00001")]), RULES
            )
            path = write_shard(root, payload)
            forged = json.loads(gzip.decompress(path.read_bytes()))
            forged["counts"]["all"] = 2
            path.write_bytes(shard_bytes(forged))

            with self.assertRaisesRegex(ValueError, "counts"):
                read_shard(path)

    def test_legacy_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = build_month(
                date(2020, 1, 2), intake([paper("2001.00001")]), RULES
            )
            payload["papers"][0]["comment"] = "Prior public annotation"
            payload["papers"][0]["abstract"] = (
                "This increasedhttps://www.overleaf.com/project/"
                "5e2b14694c5dc600017292e6 intercorrelation."
            )
            payload["papers"][0]["authors"] = [
                "Ada Researcher",
                "owner@example.org",
            ]
            path = root / "2020-01.json.gz"
            path.write_bytes(shard_bytes(payload))

            self.assertEqual(migrate_archive(root), ["2020-01"])

            saved = read_shard(path)
            self.assertEqual(saved["counts"]["all"], 1)
            self.assertEqual(saved["papers"][0]["id"], "2001.00001")
            self.assertNotIn("comment", saved["papers"][0])
            self.assertEqual(
                saved["papers"][0]["abstract"],
                "This increased intercorrelation.",
            )
            self.assertEqual(saved["papers"][0]["authors"], ["Ada Researcher"])
            self.assertEqual(migrate_archive(root), [])

    def test_known_legacy(self) -> None:
        unknown = paper("private/9901001", published="1999-01-02")
        with self.assertRaisesRegex(ValueError, "public paper text"):
            build_month(date(1999, 1, 2), intake([unknown]), RULES)

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
