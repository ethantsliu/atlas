from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from harvest import (  # noqa: E402
    advance_history,
    check_stage,
    gc_stages,
    plan_history,
    read_state,
    run_harvest,
    stage_path,
)
from oai import OaiError, Page, parse_page  # noqa: E402


def record(identifier: str, *, deleted: bool = False) -> dict:
    value = {
        "id": identifier,
        "datestamp": "2026-08-26",
        "deleted": deleted,
    }
    if not deleted:
        value.update(
            {
                "title": "A test paper",
                "abstract": "A source abstract without derived labels.",
                "authors": ["Ada Lovelace"],
                "categories": ["cs.LG"],
                "created": "2026-08-25",
                "updated": "2026-08-26",
            }
        )
    return value


@dataclass(frozen=True)
class TestPage:
    records: tuple[dict, ...]
    token: str | None
    response_date: str
    expires: str | None = None
    cursor: int | None = None
    total: int | None = None


class FakeClient:
    def __init__(self, routes: dict[str | None, list[TestPage]]) -> None:
        self.routes = routes
        self.calls = []

    def pages(self, start=None, end=None, token=None):
        self.calls.append({"start": start, "end": end, "token": token})
        yield from self.routes[token]


class HarvestTests(unittest.TestCase):
    def test_history_plan(self) -> None:
        history = {"next_year": 2005, "through_year": None, "complete": False}
        planned, generation, start, end = plan_history(history, 2026)
        self.assertEqual(
            (generation, start, end),
            ("history-2005", "2005-09-16", "2005-12-31"),
        )

        planned = advance_history(planned, generation)
        _, generation, start, end = plan_history(planned, 2026)
        self.assertEqual(
            (generation, start, end),
            ("history-2006", "2006-01-01", "2006-12-31"),
        )

    def test_complete(self) -> None:
        pages = [
            TestPage(
                (record("2608.00001"), record("2608.00002", deleted=True)),
                "next token",
                "2026-08-26T20:00:00Z",
                "2026-08-27T00:00:00Z",
                0,
                3,
            ),
            TestPage(
                (record("2608.00003"),),
                None,
                "2026-08-26T20:00:04Z",
                None,
                2,
                3,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = FakeClient({None: pages})
            manifest = run_harvest(root, "bootstrap", client)

            self.assertTrue(manifest["sealed"])
            self.assertEqual(manifest["page_count"], 2)
            self.assertEqual(manifest["record_count"], 3)
            self.assertEqual(manifest["source_total"], 3)
            self.assertEqual(manifest["tombstone_count"], 1)
            self.assertEqual(manifest["watermark"], "2026-08-26T20:00:04Z")
            self.assertEqual(
                client.calls, [{"start": None, "end": None, "token": None}]
            )
            saved = json.loads(
                gzip.decompress(
                    (
                        stage_path(root, "bootstrap") / "pages/00000000.json.gz"
                    ).read_bytes()
                )
            )
            self.assertTrue(saved["records"][1]["deleted"])
            self.assertNotIn("topics", saved["records"][0])
            self.assertNotIn("tricks", saved["records"][0])
            self.assertNotIn("scope", saved["records"][0])

    def test_incomplete_total(self) -> None:
        page = TestPage(
            (record("2608.00001"),),
            None,
            "2026-08-26T20:00:00Z",
            total=2,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "source total"):
                run_harvest(root, "short", FakeClient({None: [page]}))
            self.assertEqual(read_state(root, "short")["page_count"], 0)

    def test_cursor_gap(self) -> None:
        page = TestPage(
            (record("2608.00001"),),
            "next",
            "2026-08-26T20:00:00Z",
            cursor=4,
            total=2,
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "cursor"):
                run_harvest(Path(directory), "gap", FakeClient({None: [page]}))

    def test_total_drift(self) -> None:
        first = TestPage(
            (record("2608.00001"),),
            "next",
            "2026-08-26T20:00:00Z",
            cursor=0,
            total=2,
        )
        second = TestPage(
            (record("2608.00002"),),
            None,
            "2026-08-26T20:00:04Z",
            cursor=1,
            total=3,
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "source total changed"):
                run_harvest(
                    Path(directory), "drift", FakeClient({None: [first, second]})
                )

    def test_repeated_token(self) -> None:
        first = TestPage(
            (record("2608.00001"),),
            "same",
            "2026-08-26T20:00:00Z",
        )
        repeated = TestPage(
            (record("2608.00002"),),
            "same",
            "2026-08-26T20:00:04Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_harvest(root, "loop", FakeClient({None: [first]}), max_pages=1)
            with self.assertRaisesRegex(OaiError, "repeated"):
                run_harvest(root, "loop", FakeClient({"same": [repeated]}))
            self.assertEqual(read_state(root, "loop")["page_count"], 1)

    def test_parsed_page(self) -> None:
        source = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <responseDate>2026-08-26T20:00:00Z</responseDate>
          <ListRecords>
            <record><header><identifier>oai:arXiv.org:2608.00001</identifier>
              <datestamp>2026-08-26</datestamp></header><metadata>
              <arXiv xmlns="http://arxiv.org/OAI/arXiv/">
                <id>2608.00001</id><created>2026-08-25</created>
                <authors><author><keyname>Lovelace</keyname></author></authors>
                <title>Parsed paper</title><categories>cs.LG</categories>
                <abstract>Parsed directly from the transport.</abstract>
              </arXiv></metadata></record>
            <record><header status="deleted">
              <identifier>oai:arXiv.org:hep-th/9912345</identifier>
              <datestamp>2026-08-26</datestamp></header></record>
            <resumptionToken />
          </ListRecords></OAI-PMH>"""
        page = parse_page(source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = run_harvest(root, "parsed", FakeClient({None: [page]}))

            self.assertEqual(manifest["record_count"], 2)
            self.assertEqual(manifest["tombstone_count"], 1)
            saved = json.loads(
                gzip.decompress(
                    (stage_path(root, "parsed") / "pages/00000000.json.gz").read_bytes()
                )
            )
            self.assertEqual(saved["records"][0]["id"], "2608.00001")
            self.assertEqual(saved["records"][1]["id"], "hep-th/9912345")
            self.assertTrue(saved["records"][1]["deleted"])

    def test_resume(self) -> None:
        first = TestPage(
            (record("2608.00001"),),
            "opaque token",
            "2026-08-26T20:00:00Z",
            "2026-08-27T00:00:00Z",
        )
        final = TestPage(
            (record("2608.00002"),),
            None,
            "2026-08-26T20:01:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = FakeClient({None: [first]})
            state = run_harvest(
                root,
                "daily",
                initial,
                start="2026-08-25",
                end="2026-08-26",
                max_pages=1,
            )

            self.assertEqual(state["status"], "running")
            self.assertEqual(state["next_token"], "opaque token")
            self.assertFalse((stage_path(root, "daily") / "index.json").exists())
            resumed = FakeClient({"opaque token": [final]})
            manifest = run_harvest(
                root,
                "daily",
                resumed,
                start="2026-08-25",
                end="2026-08-26",
            )

            self.assertEqual(manifest["record_count"], 2)
            self.assertEqual(
                resumed.calls,
                [{"start": None, "end": None, "token": "opaque token"}],
            )
            self.assertEqual(
                manifest["query"]["until"],
                "2026-08-26",
            )

    def test_server_date(self) -> None:
        page = Page(records=(record("2608.00001"),), token=None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = FakeClient({None: [page]})
            with self.assertRaisesRegex(ValueError, "responseDate"):
                run_harvest(root, "missing", client)
            state = read_state(root, "missing")
            self.assertEqual(state["page_count"], 0)
            self.assertIsNone(state["watermark"])

    def test_partial_checkpoint(self) -> None:
        pages = [
            TestPage(
                (record("2608.00001"),),
                "next",
                "2026-08-26T20:00:00Z",
            ),
            TestPage((record("2608.00002"),), None, "local-time"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "responseDate"):
                run_harvest(root, "partial", FakeClient({None: pages}))
            state = read_state(root, "partial")
            self.assertEqual(state["page_count"], 1)
            self.assertEqual(state["next_token"], "next")
            self.assertTrue(
                (stage_path(root, "partial") / "pages/00000000.json.gz").exists()
            )
            self.assertFalse(
                (stage_path(root, "partial") / "pages/00000001.json.gz").exists()
            )

    def test_query_guard(self) -> None:
        first = TestPage(
            (record("2608.00001"),),
            "next",
            "2026-08-26T20:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_harvest(
                root,
                "guard",
                FakeClient({None: [first]}),
                start="2026-08-25",
                max_pages=1,
            )
            with self.assertRaisesRegex(ValueError, "query"):
                run_harvest(
                    root,
                    "guard",
                    FakeClient({"next": []}),
                    start="2026-08-26",
                )
            with self.assertRaisesRegex(ValueError, "query"):
                run_harvest(
                    root,
                    "guard",
                    FakeClient({"next": []}),
                    start="2026-08-25",
                    end="2026-08-27",
                )

    def test_integrity(self) -> None:
        final = TestPage(
            (record("2608.00001"),),
            None,
            "2026-08-26T20:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_harvest(root, "integrity", FakeClient({None: [final]}))
            path = stage_path(root, "integrity") / "pages/00000000.json.gz"
            path.write_bytes(path.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "digest"):
                check_stage(root, "integrity")

    def test_complete_noop(self) -> None:
        final = TestPage(
            (record("2608.00001"),),
            None,
            "2026-08-26T20:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_harvest(root, "sealed", FakeClient({None: [final]}))
            client = FakeClient({})
            manifest = run_harvest(root, "sealed", client)
            self.assertTrue(manifest["sealed"])
            self.assertEqual(client.calls, [])

    def test_stage_gc(self) -> None:
        final = TestPage((record("2608.00001"),), None, "2026-08-26T20:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_harvest(root, "sealed", FakeClient({None: [final]}))
            self.assertEqual(gc_stages(root, {"sealed"}), [])
            self.assertEqual(gc_stages(root, set()), ["sealed"])
            self.assertFalse(stage_path(root, "sealed").exists())

            run_harvest(root, "tampered", FakeClient({None: [final]}))
            (stage_path(root, "tampered") / "index.json").write_text(
                "{}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "manifest"):
                gc_stages(root, set())
            self.assertTrue(stage_path(root, "tampered").exists())

            outside = root / "outside"
            outside.mkdir()
            (root / "stage/link").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                gc_stages(root, {"tampered"})

    def test_generation_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "generation"):
                run_harvest(
                    Path(directory),
                    "../escape",
                    FakeClient({}),
                )


if __name__ == "__main__":
    unittest.main()
