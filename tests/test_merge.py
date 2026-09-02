from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from archive import read_manifest, read_shard  # noqa: E402
from archivecheck import validate_archive  # noqa: E402
from cloud import (  # noqa: E402
    archive_text,
    build_cloud,
    row_hash,
    validate_cloud,
)
from corpus import prep_release  # noqa: E402
from embed import EMBED_DIM, MODEL, MODEL_DIGEST  # noqa: E402
from events import filter_events, open_ledger, save_events  # noqa: E402
from harvest import run_harvest, stage_path  # noqa: E402
from merge import index_store, merge_generation, open_store  # noqa: E402
from oai import Page, parse_page  # noqa: E402
from rank import load_rules  # noqa: E402
from retrieve import check_retrieval, retrieve  # noqa: E402
from scan import scan_archive  # noqa: E402
from synth import make_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")


def paper(identifier: str, category: str, *, title: str = "A paper", updated=None):
    published = f"20{identifier[:2]}-{identifier[2:4]}-01"
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": title,
        "abstract": "We test synthetic data and controlled learning evidence.",
        "authors": ["Ada Researcher"],
        "categories": [category],
        "primary_category": category,
        "published": published,
        "updated": updated or published,
        "comment": None,
        "datestamp": updated or published,
        "deleted": False,
        "version_dates": [],
    }


def tombstone(identifier: str, stamp: str) -> dict:
    return {"id": identifier, "datestamp": stamp, "deleted": True}


class FakeClient:
    def __init__(self, pages: list[Page]) -> None:
        self.source = pages

    def pages(self, start=None, end=None, token=None):
        yield from self.source


def seal(root: Path, generation: str, records: tuple[dict, ...]) -> None:
    page = Page(
        records=records,
        token=None,
        response_date="2026-08-26T20:00:00Z",
    )
    run_harvest(root, generation, FakeClient([page]))


def seed_cloud(root: Path, archive: Path, papers: list[dict]) -> tuple[dict, Path]:
    """Build one offline cloud from deterministic nonzero vectors."""
    anchors = root / "anchors.npz"
    cache = root / "vectors"
    output = root / "cloud"
    anchor_vectors = np.eye(8, EMBED_DIM, dtype=np.float32)
    vectors = anchor_vectors[:2]
    np.savez_compressed(
        anchors,
        schema_version=1,
        model=MODEL,
        model_digest=MODEL_DIGEST,
        dimensions=EMBED_DIM,
        ids=np.asarray([f"anchor-{index}" for index in range(8)]),
        vectors=anchor_vectors,
        points=np.asarray(
            [[index * 10, index * 5, index * 2] for index in range(8)],
            dtype=np.float32,
        ),
    )
    rows = [(paper["id"], archive_text(paper)) for paper in papers]
    cache.mkdir()
    np.savez_compressed(
        cache / "1999-01.npz",
        ids=np.asarray([identifier for identifier, _ in rows]),
        hashes=np.asarray([row_hash(*row) for row in rows]),
        vectors=vectors,
        done=np.ones(2, dtype=bool),
    )
    return build_cloud(archive, anchors, cache, output, 2), output


class MergeTests(unittest.TestCase):
    def test_event_watermarks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ledger").mkdir()
            database = open_store(root / "incoming.sqlite")
            ledger = open_ledger(root / "ledger")
            try:
                database.executemany(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        ("stale", "2026-01-01T00:00:00Z", 0, 0, "2026-01", "{}"),
                        ("equal", "2026-02-01T00:00:00Z", 1, 0, "2026-02", "{}"),
                        ("newer", "2026-03-01T00:00:00Z", 2, 0, "2026-03", "{}"),
                        ("unseen", "2026-01-01T00:00:00Z", 3, 0, "2026-01", "{}"),
                    ],
                )
                ledger.executemany(
                    "INSERT INTO events VALUES (?, ?, ?, ?)",
                    [
                        ("stale", "2026-02-01T00:00:00Z", 0, "2026-01"),
                        ("equal", "2026-02-01T00:00:00Z", 0, "2026-02"),
                        ("newer", "2026-02-01T00:00:00Z", 0, "2026-03"),
                    ],
                )

                filter_events(database, ledger)
                self.assertEqual(
                    [
                        row[0]
                        for row in database.execute("SELECT id FROM events ORDER BY id")
                    ],
                    ["equal", "newer", "unseen"],
                )

                save_events(database, ledger)
                self.assertEqual(
                    ledger.execute(
                        "SELECT id, stamp FROM events ORDER BY id"
                    ).fetchall(),
                    [
                        ("equal", "2026-02-01T00:00:00Z"),
                        ("newer", "2026-03-01T00:00:00Z"),
                        ("stale", "2026-02-01T00:00:00Z"),
                        ("unseen", "2026-01-01T00:00:00Z"),
                    ],
                )
            finally:
                database.close()
                ledger.close()

            (root / "empty-ledger").mkdir()
            empty = open_store(root / "empty-incoming.sqlite")
            empty_ledger = open_ledger(root / "empty-ledger")
            try:
                empty.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                    ("first", "2026-01-01T00:00:00Z", 0, 0, "2026-01", "{}"),
                )
                filter_events(empty, empty_ledger)
                self.assertEqual(
                    empty.execute("SELECT count(*) FROM events").fetchone(), (1,)
                )
            finally:
                empty.close()
                empty_ledger.close()

    def test_store_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = open_store(Path(directory) / "events.sqlite")
            try:
                index_store(database)
                columns = database.execute("PRAGMA index_info(event_month)").fetchall()
                plan = database.execute(
                    "EXPLAIN QUERY PLAN SELECT id, paper FROM events "
                    "WHERE deleted=0 AND month=? ORDER BY id",
                    ("2026-08",),
                ).fetchall()
            finally:
                database.close()

        self.assertEqual([row[2] for row in columns], ["month", "id"])
        self.assertIn("event_month", str(plan))

    def test_parser_seam(self) -> None:
        source = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <responseDate>2026-08-26T20:00:00Z</responseDate><ListRecords>
          <record><header><identifier>oai:arXiv.org:2608.00001</identifier>
          <datestamp>2026-08-26</datestamp></header><metadata>
          <arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>2608.00001</id>
          <created>2026-08-25</created><authors><author>
          <keyname>Lovelace</keyname><forenames>Ada</forenames></author></authors>
          <title>Parsed paper</title><categories>cs.LG</categories>
          <abstract>We introduce synthetic data for learning.</abstract>
          </arXiv></metadata></record><resumptionToken /></ListRecords></OAI-PMH>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            run_harvest(harvest, "parsed", FakeClient([parse_page(source)]))

            manifest = merge_generation(harvest, "parsed", archive, RULES)
            saved = read_shard(archive / "2026-08.json.gz")["papers"][0]

            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(saved["id"], "2608.00001")
            self.assertEqual(saved["published"], "2026-08-25")
            self.assertEqual(saved["scope"], "likely")

    def test_raw_seam(self) -> None:
        source = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <responseDate>2005-09-16T12:00:00Z</responseDate><ListRecords>
          <record><header><identifier>oai:arXiv.org:hep-th/9901001</identifier>
          <datestamp>2005-09-16</datestamp></header><metadata>
          <arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/">
          <id>hep-th/9901001</id><submitter>private@example.org</submitter>
          <version version="v1"><date>Fri, 1 Jan 1999</date>
          <size>10kb</size><source_type>TeX</source_type></version>
          <version version="v2"><date>Mon, 4 Jan 1999 23:30:00 GMT</date>
          <size>12kb</size><source_type>TeX</source_type></version>
          <title>Legacy sparse routing agents</title>
          <authors>Doe, J. and Roe, R.</authors>
          <categories>hep-th cs.LG</categories><abstract>We propose a sparse routing
          algorithm for controlled agents and learning.</abstract>
          </arXivRaw></metadata></record><resumptionToken />
          </ListRecords></OAI-PMH>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            parsed = parse_page(source)
            second = {
                **parsed.records[0],
                "id": "hep-th/9901002",
                "url": "https://arxiv.org/abs/hep-th/9901002",
                "title": "Another legacy sparse routing agent",
            }
            page = Page(
                records=(parsed.records[0], second),
                token=None,
                response_date=parsed.response_date,
            )
            run_harvest(harvest, "legacy", FakeClient([page]))

            manifest = merge_generation(harvest, "legacy", archive, RULES)
            saved = read_shard(archive / "1999-01.json.gz")["papers"][0]

            self.assertEqual(manifest["counts"]["all"], 2)
            self.assertEqual(saved["id"], "hep-th/9901001")
            self.assertEqual(saved["published"], "1999-01-01")
            self.assertEqual(saved["updated"], "1999-01-04")
            self.assertNotIn("submitter", saved)
            self.assertNotIn("comment", saved)

            release = root / "release"
            plan = prep_release(archive, release)
            promoted = read_manifest(release)
            strict = read_shard(release / promoted["shards"][0]["path"])
            self.assertEqual(plan["months"], ["1999-01"])
            self.assertEqual(
                [row["id"] for row in strict["papers"]][:1], ["hep-th/9901001"]
            )
            self.assertNotIn("private@example.org", str(strict))

            sources = [
                {
                    "source_id": "arxiv:1999-01",
                    "sha256": promoted["shards"][0]["sha256"],
                }
            ]
            corpus = make_manifest("legacy-flow-1", sources)
            discovered = scan_archive(release, promoted, corpus, 4)
            candidate = discovered["candidates"][0]
            queue = retrieve(candidate, strict["papers"])
            self.assertIs(check_retrieval(queue), queue)
            self.assertIn("arxiv:hep-th/9901001", candidate["support_ids"])

            cloud_manifest, cloud = seed_cloud(root, archive, strict["papers"])
            self.assertEqual(cloud_manifest["count"], 2)
            self.assertEqual(validate_cloud(archive, cloud), cloud_manifest)

        malformed = source.replace(b"Mon, 4 Jan 1999 23:30:00 GMT", b"not a date")
        with self.assertRaisesRegex(ValueError, "invalid date"):
            parse_page(malformed)

    def test_archive_seam(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            records = (
                paper("2607.00001", "cs.LG"),
                paper("2607.00002", "math.AT"),
                paper("2608.00001", "physics.optics"),
            )
            seal(harvest, "bootstrap", records)

            manifest = merge_generation(harvest, "bootstrap", archive, RULES, workers=2)

            self.assertEqual(manifest["counts"]["all"], 3)
            self.assertEqual(manifest["counts"]["likely"], 1)
            self.assertEqual(manifest["counts"]["possible"], 1)
            self.assertEqual(manifest["counts"]["outside"], 1)
            self.assertEqual(validate_archive(archive), manifest)
            july = read_shard(archive / "2026-07.json.gz")
            self.assertEqual(july["days"], [])
            self.assertEqual(
                [row["id"] for row in july["papers"]], ["2607.00001", "2607.00002"]
            )
            self.assertEqual(
                set(july["papers"][0]),
                {
                    "id",
                    "url",
                    "title",
                    "abstract",
                    "authors",
                    "categories",
                    "primary_category",
                    "published",
                    "updated",
                    "scope",
                    "relevance",
                    "interest",
                    "topics",
                    "tricks",
                },
            )
            self.assertIn("synthetic data", archive_text(july["papers"][0]))
            self.assertNotIn("comment", july["papers"][0])
            sources = [
                {"source_id": f"arxiv:{row['month']}", "sha256": row["sha256"]}
                for row in manifest["shards"]
            ]
            scanned = scan_archive(
                archive, manifest, make_manifest("merge-test-1", sources), 4
            )
            self.assertEqual(scanned["loaded_months"], ["2026-07", "2026-08"])
            self.assertEqual(scanned["loaded_papers"], 2)

    def test_tombstone_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            seal(
                harvest,
                "first",
                (
                    paper("2608.00001", "cs.LG", title="Old title"),
                    paper("2608.00002", "cs.LG"),
                ),
            )
            merge_generation(harvest, "first", archive, RULES)
            seal(
                harvest,
                "second",
                (
                    paper(
                        "2608.00001",
                        "cs.LG",
                        title="New title",
                        updated="2026-08-20",
                    ),
                    tombstone("2608.00002", "2026-08-20"),
                ),
            )

            manifest = merge_generation(harvest, "second", archive, RULES)
            payload = read_shard(archive / "2026-08.json.gz")

            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(payload["papers"][0]["title"], "New title")
            self.assertEqual(payload["papers"][0]["published"], "2026-08-01")

    def test_month_move(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            original = paper("2608.00001", "cs.LG", title="Original month")
            seal(harvest, "first", (original,))
            merge_generation(harvest, "first", archive, RULES)
            corrected = {
                **original,
                "title": "Corrected month",
                "published": "2026-07-31",
                "updated": "2026-08-20",
                "datestamp": "2026-08-20",
            }
            seal(harvest, "second", (corrected,))

            manifest = merge_generation(harvest, "second", archive, RULES)

            july = read_shard(archive / "2026-07.json.gz")
            august = read_shard(archive / "2026-08.json.gz")
            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual([row["id"] for row in july["papers"]], ["2608.00001"])
            self.assertEqual(august["papers"], [])

    def test_public_boundary(self) -> None:
        unsafe = ({"id": "private-paper"},)
        for index, changes in enumerate(unsafe):
            with (
                self.subTest(changes=changes),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                harvest = root / "harvest"
                record = {**paper(f"2608.{index + 1:05d}", "cs.LG"), **changes}
                seal(harvest, "unsafe", (record,))
                with self.assertRaisesRegex(ValueError, "public paper text"):
                    merge_generation(harvest, "unsafe", root / "archive", RULES)

    def test_error_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            record = {**paper("2608.00001", "cs.LG"), "title": "Q1: Why?"}
            seal(harvest, "unsafe-title", (record,))
            with self.assertRaisesRegex(
                ValueError, r"public paper text is invalid: 2608\.00001"
            ):
                merge_generation(harvest, "unsafe-title", root / "archive", RULES)

    def test_control_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            record = {**paper("2608.00001", "cs.LG"), "title": "Left\u202eright"}
            seal(harvest, "controls", (record,))

            merge_generation(harvest, "controls", root / "archive", RULES)

            saved = read_shard(root / "archive/2026-08.json.gz")["papers"][0]
            self.assertEqual(saved["title"], "Left right")

    def test_scholarly_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            record = {
                **paper("2608.00001", "cs.LG"),
                "abstract": (
                    "Code is available at https://github.com/public-lab/public-paper."
                ),
                "authors": ["Ada Researcher <ada@university.edu>"],
            }
            seal(harvest, "public", (record,))

            merge_generation(harvest, "public", root / "archive", RULES)

            saved = read_shard(root / "archive/2026-08.json.gz")["papers"][0]
            self.assertIn("github.com", saved["abstract"])
            self.assertEqual(saved["authors"], ["Ada Researcher"])

    def test_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            seal(harvest, "repeat", (paper("2608.00001", "cs.LG"),))
            first = merge_generation(harvest, "repeat", archive, RULES)
            content = (archive / "2026-08.json.gz").read_bytes()

            second = merge_generation(harvest, "repeat", archive, RULES)

            self.assertEqual(second, first)
            self.assertEqual((archive / "2026-08.json.gz").read_bytes(), content)

    def test_asset_retire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            first = root / "first"
            second = root / "second"
            july = paper("2607.00001", "cs.LG", title="Unchanged")
            august = paper("2608.00001", "cs.LG", title="Original")
            seal(harvest, "initial", (july, august))
            merge_generation(harvest, "initial", archive, RULES)
            prep_release(archive, first)
            prior = read_manifest(first)
            old_paths = {row["month"]: row["path"] for row in prior["shards"]}
            changed = {
                **august,
                "title": "Changed",
                "updated": "2026-08-20",
                "datestamp": "2026-08-20",
            }
            seal(harvest, "update", (changed,))
            merge_generation(harvest, "update", archive, RULES)

            plan = prep_release(archive, second, first / "index.json")
            current = read_manifest(second)
            new_paths = {row["month"]: row["path"] for row in current["shards"]}

            self.assertEqual(plan["months"], ["2026-08"])
            self.assertEqual(plan["assets"], [new_paths["2026-08"]])
            self.assertEqual(plan["keep"], sorted(new_paths.values()))
            self.assertIn(old_paths["2026-07"], plan["keep"])
            self.assertNotIn(old_paths["2026-08"], plan["keep"])

    def test_older_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            seal(
                harvest,
                "newer",
                (
                    paper(
                        "2608.00001",
                        "cs.LG",
                        title="Keep me",
                        updated="2026-08-20",
                    ),
                ),
            )
            merge_generation(harvest, "newer", archive, RULES)
            seal(
                harvest,
                "older",
                (
                    paper(
                        "2608.00001",
                        "cs.LG",
                        title="Stale",
                        updated="2026-08-10",
                    ),
                ),
            )

            merge_generation(harvest, "older", archive, RULES)

            payload = read_shard(archive / "2026-08.json.gz")
            self.assertEqual(payload["papers"][0]["title"], "Keep me")

    def test_source_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            current = paper(
                "2608.00001", "cs.LG", title="Old source", updated="2026-08-20"
            )
            seal(harvest, "current", (current,))
            merge_generation(harvest, "current", archive, RULES)
            corrected = {
                **current,
                "title": "Corrected source",
                "updated": "2026-08-10",
                "datestamp": "2026-08-21",
            }
            seal(harvest, "corrected", (corrected,))

            merge_generation(harvest, "corrected", archive, RULES)

            saved = read_shard(archive / "2026-08.json.gz")["papers"][0]
            self.assertEqual(saved["title"], "Corrected source")
            self.assertEqual(saved["updated"], "2026-08-10")

    def test_stale_move(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            current = paper(
                "2608.00001", "cs.LG", title="Keep August", updated="2026-08-20"
            )
            seal(harvest, "current", (current,))
            merge_generation(harvest, "current", archive, RULES)
            stale = {
                **current,
                "title": "Stale July",
                "published": "2026-07-31",
                "updated": "2026-08-10",
                "datestamp": "2026-08-10",
            }
            seal(harvest, "stale", (stale,))

            manifest = merge_generation(harvest, "stale", archive, RULES)

            august = read_shard(archive / "2026-08.json.gz")
            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(august["papers"][0]["title"], "Keep August")
            self.assertFalse((archive / "2026-07.json.gz").exists())

    def test_stale_tombstone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            seal(
                harvest,
                "current",
                (paper("2608.00001", "cs.LG", updated="2026-08-20"),),
            )
            merge_generation(harvest, "current", archive, RULES)
            seal(
                harvest,
                "stale",
                (tombstone("2608.00001", "2026-08-10"),),
            )

            manifest = merge_generation(harvest, "stale", archive, RULES)

            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertEqual(
                read_shard(archive / "2026-08.json.gz")["papers"][0]["id"],
                "2608.00001",
            )
            self.assertTrue((archive / "events.sqlite").is_file())

    def test_stale_resurrection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            seal(
                harvest,
                "deleted",
                (tombstone("2608.00001", "2026-08-20"),),
            )
            merge_generation(harvest, "deleted", archive, RULES)
            seal(
                harvest,
                "stale",
                (paper("2608.00001", "cs.LG", updated="2026-08-10"),),
            )

            manifest = merge_generation(harvest, "stale", archive, RULES)

            self.assertEqual(manifest["counts"]["all"], 0)
            self.assertFalse((archive / "2026-08.json.gz").exists())

    def test_unsealed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            stage_path(harvest, "open").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "sealed"):
                merge_generation(harvest, "open", root / "archive", RULES)

    def test_invalid_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harvest = root / "harvest"
            archive = root / "archive"
            invalid = paper("2608.00001", "cs.LG")
            invalid["published"] = "August 2026"
            seal(harvest, "invalid", (invalid,))
            with self.assertRaisesRegex(ValueError, "published"):
                merge_generation(harvest, "invalid", archive, RULES)


if __name__ == "__main__":
    unittest.main()
