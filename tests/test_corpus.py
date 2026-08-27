from __future__ import annotations

import gzip
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from corpus import (  # noqa: E402
    ack_pending,
    check_root,
    merge_pending,
    pack_root,
    prep_release,
    read_cursor,
    run_corpus,
    unpack_root,
    write_cursor,
)
from oai import OaiClient, OaiError  # noqa: E402
from archive import read_shard, shard_bytes, write_manifest  # noqa: E402
from archivecheck import validate_archive  # noqa: E402


def paper(identifier: str) -> dict:
    return {"id": identifier, "datestamp": "2026-08-26", "deleted": False}


@dataclass(frozen=True)
class TestPage:
    records: tuple[dict, ...]
    token: str | None
    response_date: str
    expires: str | None = None


class FakeClient:
    delay = 3.1

    def __init__(self, routes: dict[str | None, list[TestPage]]) -> None:
        self.routes = routes
        self.calls = []

    def pages(self, start=None, end=None, token=None):
        self.calls.append({"start": start, "end": end, "token": token})
        yield from self.routes[token]


class TimedClient(FakeClient):
    def __init__(self, routes, clock) -> None:
        super().__init__(routes)
        self.clock = clock

    def pages(self, start=None, end=None, token=None):
        self.clock.value += 4
        yield from super().pages(start, end, token)


class ResetClient:
    delay = 3.1

    def __init__(self) -> None:
        self.calls = []
        self.started = 0

    def pages(self, start=None, end=None, token=None):
        self.calls.append({"start": start, "end": end, "token": token})
        if token == "stale":
            raise OaiError("badResumptionToken", "server rejected token")
        self.started += 1
        if self.started == 1:
            yield TestPage(
                (paper("1"),),
                "stale",
                "2026-08-27T00:17:00Z",
            )
        else:
            yield TestPage((paper("2"),), None, "2026-08-27T00:18:00Z")


class Clock:
    def __init__(self) -> None:
        self.value = 0.0
        self.waits = []

    def read(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.value += seconds


NOW = datetime(2026, 8, 27, 0, 17, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def full_paper(identifier: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A semantic learning paper",
        "abstract": "We test synthetic data with controlled evidence.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2026-08-26",
        "updated": "2026-08-26",
        "comment": None,
        "datestamp": "2026-08-26",
        "deleted": False,
        "version_dates": [],
    }


def seed_cursor(root: Path, watermark: str) -> None:
    """Create a completed-history cursor for incremental-only tests."""
    write_cursor(
        root,
        {
            "schema_version": 1,
            "watermark": watermark,
            "active": None,
            "last_generation": "history-2026",
            "pending": [],
            "merged": [],
            "history": {
                "next_year": 2027,
                "through_year": 2026,
                "complete": True,
            },
        },
    )


class CorpusTests(unittest.TestCase):
    def test_workflow_policy(self) -> None:
        corpus = (ROOT / ".github/workflows/corpus.yml").read_text(encoding="utf-8")
        legacy = (ROOT / ".github/workflows/archive.yml").read_text(encoding="utf-8")
        discover = (ROOT / ".github/workflows/discover.yml").read_text(encoding="utf-8")
        feed = (ROOT / ".github/workflows/feed.yml").read_text(encoding="utf-8")

        for required in (
            'cron: "17 04,10,16,22 * * *"',
            "cancel-in-progress: false",
            "PROMOTED_TAG: corpus-v2",
            "MIN_READY: 50000",
            'if [ "$paper_count" -gt "$MIN_READY" ]; then',
            'swap_asset "$PROMO_ROOT/index.json" index.json index',
            'swap_asset "$PROMO_ROOT/cloud-ready.json" cloud-ready.json ready',
            'pointer_name="pointer-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-${archive_digest:0:16}.json"',
            "awk -F '\\t' '$2 ~ /^pointer-",
            'event_type:"corpus-promoted"',
            "cloud-ready.json",
            "history_complete:true",
            "steps.prep.outputs.ready == 'true'",
            "if: steps.merge.outputs.promote == 'true' && steps.prep.outputs.ready == 'true'",
            "actions/upload-artifact@v4",
            'name = f"checkpoint-{archive_hash[:16]}',
            "status=$(awk '/^HTTP/{code=$2} END{print code}' \"$probe\")",
            'if [ "$status" = "404" ]; then',
            "archive_hash = file_hash(archive)",
            '"bytes": target.stat().st_size',
        ):
            self.assertIn(required, corpus)
        self.assertEqual(corpus.count("Could not inspect"), 2)
        self.assertNotIn("archive.read_bytes()", corpus)
        self.assertNotIn("content = path.read_bytes()", corpus)
        self.assertNotIn("--clobber || true", corpus)
        self.assertLess(
            corpus.index('gh release upload "$PROMOTED_TAG" "$PROMO_ROOT/$asset"'),
            corpus.index("swap_asset()"),
        )
        self.assertLess(
            corpus.index('gh release upload "$PROMOTED_TAG" "$PROMO_ROOT/$recovery"'),
            corpus.index('-f name="$stable"'),
        )
        self.assertNotIn(
            'gh release upload "$PROMOTED_TAG" "$PROMO_ROOT/index.json" --clobber',
            corpus,
        )
        self.assertNotIn(
            'gh release upload "$PROMOTED_TAG" "$PROMO_ROOT/cloud-ready.json" --clobber',
            corpus,
        )
        self.assertNotIn(
            'gh release upload "$CHECKPOINT_TAG" "$CHECKPOINT_ROOT/$name" --clobber',
            corpus,
        )
        self.assertNotIn(
            'gh release upload "$CHECKPOINT_TAG" "$CHECKPOINT_POINTER" --clobber',
            corpus,
        )
        self.assertLess(
            corpus.index("Verify promoted release"),
            corpus.index("Dispatch validated promotion"),
        )
        self.assertLess(
            corpus.index('cmp "$PROMO_ROOT/cloud-ready.json"'),
            corpus.index("Dispatch validated promotion"),
        )
        self.assertLess(
            corpus.index("Dispatch validated promotion"),
            corpus.index("Acknowledge promotion"),
        )
        retire = corpus[
            corpus.index("- name: Retire stale shard assets") : corpus.index(
                "- name: Enforce harvest result"
            )
        ]
        self.assertIn("steps.prep.outputs.ready == 'true'", retire)
        self.assertIn("steps.verify_promo.outcome == 'success'", retire)
        self.assertNotIn("schedule:", legacy)
        self.assertIn("group: arxiv-oai-corpus", legacy)
        self.assertIn("group: arxiv-oai-corpus", feed)
        self.assertIn('default: "corpus-v2"', discover)

    def test_backfill_chain(self) -> None:
        corpus = (ROOT / ".github/workflows/corpus.yml").read_text(encoding="utf-8")
        chain = corpus[
            corpus.index("- name: Continue historical backfill") : corpus.index(
                "- name: Enforce harvest result"
            )
        ]

        for guard in (
            "steps.harvest.outcome == 'success'",
            "steps.checkpoint.outcome == 'success'",
            "steps.merge.outcome == 'success'",
            "steps.package.outcome == 'success'",
            "steps.checkpoint_release.outcome == 'success'",
            "steps.merge.outputs.promote == 'false'",
            "steps.prep.outcome == 'success'",
            "steps.acknowledge.outcome == 'success'",
            ".prior_page_count",
            ".page_count > .prior_page_count",
            '.reason == "sealed"',
            '.reason == "page-limit"',
            '.reason == "time-limit"',
            ".history.complete == false",
            ".pending == []",
            ".merged == []",
            ".active.generation == $result[0].generation",
            "if ! jq -e",
            "safely checkpointed",
            "gh workflow run corpus.yml",
            '-f pages="$CHAIN_PAGES"',
            '-f minutes="$CHAIN_MINUTES"',
        ):
            self.assertIn(guard, chain)
        self.assertNotIn('.reason == "token-expiring"', chain)
        self.assertIn('CHAIN_PAGES: "5000"', chain)
        self.assertIn('CHAIN_MINUTES: "300"', chain)
        self.assertNotIn("inputs.pages", chain)
        self.assertNotIn("inputs.minutes", chain)
        self.assertIn("actions: write", corpus)
        self.assertLess(
            corpus.index("- name: Publish release checkpoint"),
            corpus.index("- name: Continue historical backfill"),
        )

    def test_cadence(self) -> None:
        first = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <responseDate>2026-08-27T00:17:00Z</responseDate><ListRecords>
          <record><header status="deleted"><identifier>oai:arXiv.org:2608.00001</identifier>
          <datestamp>2026-08-26</datestamp></header></record>
          <resumptionToken expirationDate="2026-08-28T00:00:00Z">opaque</resumptionToken>
          </ListRecords></OAI-PMH>"""
        final = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <responseDate>2026-08-27T00:17:05Z</responseDate><ListRecords>
          <record><header status="deleted"><identifier>oai:arXiv.org:2608.00002</identifier>
          <datestamp>2026-08-26</datestamp></header></record>
          <resumptionToken /></ListRecords></OAI-PMH>"""
        payloads = iter((first, final))

        class Response(io.BytesIO):
            headers = {}

        def opener(request, timeout):
            return Response(next(payloads))

        clock = Clock()
        client = OaiClient(
            opener=opener,
            sleeper=clock.sleep,
            clock=clock.read,
            now=lambda: NOW,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = run_corpus(
                Path(directory),
                client,
                max_pages=2,
                max_minutes=5,
                clock=clock.read,
                wall=lambda: NOW,
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(clock.waits, [3.1])

    def test_bootstrap(self) -> None:
        pages = [
            TestPage(
                (paper("1"),),
                "next",
                "2026-08-27T00:17:00Z",
                "2026-08-28T00:00:00Z",
            ),
            TestPage((paper("2"),), None, "2026-08-27T00:17:05Z"),
        ]
        clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = FakeClient({None: [pages[0]], "next": [pages[1]]})
            result = run_corpus(
                root,
                client,
                max_pages=10,
                max_minutes=5,
                clock=clock.read,
                wall=lambda: NOW,
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(
                client.calls,
                [
                    {
                        "start": "2005-09-16",
                        "end": "2005-12-31",
                        "token": None,
                    },
                    {"start": None, "end": None, "token": "next"},
                ],
            )
            self.assertEqual(clock.value, 0)
            cursor = read_cursor(root)
            self.assertIsNone(cursor["active"])
            self.assertEqual(cursor["watermark"], "2026-08-27T00:17:00Z")
            self.assertEqual(cursor["history"]["next_year"], 2006)
            self.assertFalse(cursor["history"]["complete"])

    def test_incremental(self) -> None:
        final = TestPage((paper("1"),), None, "2026-08-27T00:17:00Z")
        update = TestPage((paper("2"),), None, "2026-08-28T00:17:00Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_cursor(root, final.response_date)
            client = FakeClient({None: [update]})
            result = run_corpus(
                root,
                client,
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW.replace(day=28),
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["start"], "2026-08-27")
            self.assertEqual(client.calls[0]["start"], "2026-08-27")
            self.assertIsNone(client.calls[0]["end"])

    def test_midnight_overlap(self) -> None:
        first = TestPage(
            (full_paper("2608.00001"),),
            "next",
            "2026-08-27T23:59:59Z",
            "2026-08-29T00:00:00Z",
        )
        final = TestPage((full_paper("2608.00002"),), None, "2026-08-28T00:00:05Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_cursor(root, "2026-08-27T23:50:00Z")
            partial = run_corpus(
                root,
                FakeClient({None: [first]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            self.assertEqual(partial["status"], "partial")
            result = run_corpus(
                root,
                FakeClient({"next": [final]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW.replace(day=28),
            )

            self.assertEqual(result["watermark"], "2026-08-27T23:59:59Z")
            archive = root / "archive"
            merge_pending(root, archive, ROOT / "data/source/feed.json")
            ack_pending(root, [result["generation"]])
            client = FakeClient(
                {
                    None: [
                        TestPage(
                            (full_paper("2608.00003"),),
                            None,
                            "2026-08-28T00:01:00Z",
                        )
                    ]
                }
            )
            run_corpus(
                root,
                client,
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW.replace(day=28),
            )
            self.assertEqual(client.calls[0]["start"], "2026-08-27")

    def test_resume(self) -> None:
        first = TestPage(
            (paper("1"),),
            "opaque",
            "2026-08-27T00:17:00Z",
            "2026-08-28T00:00:00Z",
        )
        final = TestPage((paper("2"),), None, "2026-08-27T00:18:00Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial = run_corpus(
                root,
                FakeClient({None: [first]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            self.assertEqual(partial["status"], "partial")
            self.assertEqual(partial["prior_page_count"], 0)
            client = FakeClient({"opaque": [final]})
            complete = run_corpus(
                root,
                client,
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )

            self.assertEqual(complete["status"], "complete")
            self.assertEqual(complete["prior_page_count"], 1)
            self.assertEqual(client.calls[0]["token"], "opaque")

    def test_token_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = ResetClient()
            result = run_corpus(
                Path(directory),
                client,
                max_pages=2,
                max_minutes=5,
                wall=lambda: NOW,
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["pages_this_run"], 2)
            self.assertEqual(result["prior_page_count"], 0)
            self.assertEqual(result["page_count"], 1)
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(
                [row["token"] for row in client.calls], [None, "stale", None]
            )

    def test_reset_progress(self) -> None:
        first = TestPage((paper("1"),), "stale", "2026-08-27T00:17:00Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_corpus(
                root,
                FakeClient({None: [first]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            result = run_corpus(
                root,
                ResetClient(),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["pages_this_run"], 1)
            self.assertEqual(result["prior_page_count"], 1)
            self.assertEqual(result["page_count"], 1)

    def test_expiry(self) -> None:
        page = TestPage(
            (paper("1"),),
            "opaque",
            "2026-08-27T23:40:00Z",
            "2026-08-28T00:00:00Z",
        )
        near = datetime(2026, 8, 27, 23, 50, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_corpus(
                root,
                FakeClient({None: [page]}),
                max_pages=2,
                max_minutes=5,
                wall=lambda: near,
            )

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["reason"], "token-expiring")
            self.assertEqual(result["pages_this_run"], 1)

            restarted = FakeClient(
                {None: [TestPage((paper("2"),), None, "2026-08-28T00:20:00Z")]}
            )
            complete = run_corpus(
                root,
                restarted,
                max_pages=1,
                max_minutes=5,
                wall=lambda: datetime(2026, 8, 28, 0, 20, tzinfo=timezone.utc),
            )
            self.assertEqual(complete["status"], "complete")
            self.assertEqual(complete["record_count"], 1)
            self.assertEqual(
                restarted.calls,
                [
                    {
                        "start": "2005-09-16",
                        "end": "2005-12-31",
                        "token": None,
                    }
                ],
            )

    def test_time_limit(self) -> None:
        first = TestPage(
            (paper("1"),),
            "next",
            "2026-08-27T00:17:00Z",
            "2026-08-28T00:00:00Z",
        )
        clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            result = run_corpus(
                Path(directory),
                TimedClient({None: [first]}, clock),
                max_pages=10,
                max_minutes=0.05,
                clock=clock.read,
                wall=lambda: NOW,
            )

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["reason"], "time-limit")
            self.assertEqual(result["pages_this_run"], 1)

    def test_archive(self) -> None:
        final = TestPage((paper("1"),), None, "2026-08-27T00:17:00Z")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            archive = base / "corpus.tar.gz"
            restored = base / "restored"
            run_corpus(
                source,
                FakeClient({None: [final]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            pack_root(source, archive)
            unpack_root(archive, restored)

            report = check_root(restored)
            self.assertEqual(report["cursor"]["watermark"], "2026-08-27T00:17:00Z")
            self.assertEqual(report["generations"][0]["records"], 1)

    def test_window_archive(self) -> None:
        first = TestPage(
            (paper("1"),),
            "window-token",
            "2026-08-27T00:17:00Z",
            "2026-08-28T00:00:00Z",
        )
        final = TestPage((paper("2"),), None, "2026-08-27T00:18:00Z")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            archive = base / "corpus.tar.gz"
            restored = base / "restored"
            run_corpus(
                source,
                FakeClient({None: [first]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            pack_root(source, archive)
            unpack_root(archive, restored)

            cursor = read_cursor(restored)
            self.assertEqual(cursor["active"]["start"], "2005-09-16")
            self.assertEqual(cursor["active"]["end"], "2005-12-31")
            self.assertEqual(cursor["history"]["through_year"], 2026)
            client = FakeClient({"window-token": [final]})
            result = run_corpus(
                restored,
                client,
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            self.assertEqual(result["generation"], "history-2005")
            self.assertEqual(
                client.calls,
                [{"start": None, "end": None, "token": "window-token"}],
            )

    def test_promotion(self) -> None:
        final = TestPage((full_paper("2608.00001"),), None, "2026-08-27T00:17:00Z")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "corpus"
            archive = root / "archive"
            first = base / "first"
            second = base / "second"
            run_corpus(
                root,
                FakeClient({None: [final]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )

            merged = merge_pending(root, archive, ROOT / "data/source/feed.json")
            plan = prep_release(archive, first)

            self.assertEqual(merged["pending"], ["history-2005"])
            self.assertEqual(plan["months"], ["2026-08"])
            asset = plan["assets"][0]
            self.assertRegex(asset, r"^2026-08-[0-9a-f]{16}\.json\.gz$")
            self.assertTrue((first / asset).is_file())
            remote = base / "remote"
            remote.mkdir()
            shutil.copyfile(first / "index.json", remote / "index.json")
            shutil.copyfile(first / asset, remote / asset)
            self.assertEqual(validate_archive(remote)["counts"]["all"], 1)
            repeat = prep_release(archive, second, first / "index.json")
            self.assertEqual(repeat["assets"], [])
            cursor = ack_pending(root, ["history-2005"])
            self.assertEqual(cursor["pending"], [])
            self.assertFalse((root / "stage/history-2005").exists())
            (archive / "2026-08.json.gz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "invalid"):
                pack_root(root, base / "invalid.tar.gz")

    def test_promo_scrub(self) -> None:
        final = TestPage((full_paper("2608.00001"),), None, "2026-08-27T00:17:00Z")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "corpus"
            archive = root / "archive"
            output = base / "public"
            run_corpus(
                root,
                FakeClient({None: [final]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            merge_pending(root, archive, ROOT / "data/source/feed.json")
            path = archive / "2026-08.json.gz"
            forged = json.loads(gzip.decompress(path.read_bytes()))
            forged["papers"][0]["abstract"] = (
                "This increasedhttps://www.overleaf.com/project/"
                "5e2b14694c5dc600017292e6 intercorrelation."
            )
            forged["papers"][0]["authors"] = ["Ada <ada@example.org>"]
            forged["papers"][0]["comment"] = "https://twitter.com/private/status/1"
            path.write_bytes(shard_bytes(forged))

            plan = prep_release(archive, output)

            paper = read_shard(output / plan["assets"][0])["papers"][0]
            self.assertEqual(paper["abstract"], "This increased intercorrelation.")
            self.assertEqual(paper["authors"], ["Ada"])
            self.assertNotIn("comment", paper)

    def test_dirty_restore(self) -> None:
        final = TestPage((full_paper("2608.00001"),), None, "2026-08-27T00:17:00Z")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            archive = source / "archive"
            checkpoint = base / "checkpoint.tar.gz"
            restored = base / "restored"
            output = base / "public"
            run_corpus(
                source,
                FakeClient({None: [final]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            merge_pending(source, archive, ROOT / "data/source/feed.json")
            path = archive / "2026-08.json.gz"
            forged = read_shard(path)
            forged["papers"][0]["abstract"] = (
                "Draft at https://www.overleaf.com/project/"
                "5e2b14694c5dc600017292e6 before release."
            )
            forged["papers"][0]["authors"] = ["Ada <ada@example.org>"]
            path.write_bytes(shard_bytes(forged))
            write_manifest(archive)
            pack_root(source, checkpoint)

            unpack_root(checkpoint, restored)
            plan = prep_release(restored / "archive", output)

            paper = read_shard(output / plan["assets"][0])["papers"][0]
            self.assertEqual(paper["abstract"], "Draft at before release.")
            self.assertEqual(paper["authors"], ["Ada"])

    def test_ack_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "pending"):
                ack_pending(root, ["missing"])

    def test_windows(self) -> None:
        first = TestPage((full_paper("0501.0001"),), None, "2026-08-27T00:17:00Z")
        second = TestPage((full_paper("0601.0001"),), None, "2026-08-27T00:18:00Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            run_corpus(
                root,
                FakeClient({None: [first]}),
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )
            with self.assertRaisesRegex(RuntimeError, "acknowledged"):
                run_corpus(
                    root,
                    FakeClient({None: [second]}),
                    max_pages=1,
                    max_minutes=5,
                    wall=lambda: NOW,
                )
            merge_pending(root, archive, ROOT / "data/source/feed.json")
            ack_pending(root, ["history-2005"])

            client = FakeClient({None: [second]})
            result = run_corpus(
                root,
                client,
                max_pages=1,
                max_minutes=5,
                wall=lambda: NOW,
            )

            self.assertEqual(result["generation"], "history-2006")
            self.assertEqual(result["start"], "2006-01-01")
            self.assertEqual(result["end"], "2006-12-31")
            self.assertEqual(
                client.calls,
                [
                    {
                        "start": "2006-01-01",
                        "end": "2006-12-31",
                        "token": None,
                    }
                ],
            )

    def test_unsafe_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive = base / "unsafe.tar.gz"
            content = b"escape"
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo("../escape")
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                unpack_root(archive, base / "restore")

    def test_cursor_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            (root / "cursor.json").write_text(
                json.dumps({"schema_version": 9}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "contract"):
                read_cursor(root)


if __name__ == "__main__":
    unittest.main()
