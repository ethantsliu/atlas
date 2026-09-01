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
from corpusbatch import run_batch  # noqa: E402
from oai import OaiClient, OaiError  # noqa: E402
from archive import read_shard, shard_bytes  # noqa: E402
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
    def test_batch_history(self) -> None:
        class BatchClient:
            delay = 3.1

            def __init__(self) -> None:
                self.calls = []
                self.pageset = [
                    TestPage((paper("2501.00001"),), None, "2025-12-31T23:00:00Z"),
                    TestPage((paper("2601.00001"),), None, "2026-08-27T00:10:00Z"),
                ]

            def pages(self, start=None, end=None, token=None):
                self.calls.append({"start": start, "end": end, "token": token})
                yield self.pageset.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_cursor(
                root,
                {
                    "schema_version": 1,
                    "watermark": "2024-12-31T23:00:00Z",
                    "active": None,
                    "last_generation": "history-2024",
                    "pending": [],
                    "merged": [],
                    "history": {
                        "next_year": 2025,
                        "through_year": 2026,
                        "complete": False,
                    },
                },
            )
            client = BatchClient()
            result = run_batch(
                root,
                client,
                max_pages=10,
                max_minutes=5,
                wall=lambda: NOW,
            )

            self.assertEqual(
                result["batch_generations"], ["history-2025", "history-2026"]
            )
            self.assertEqual(result["batch_pages"], 2)
            self.assertTrue(read_cursor(root)["history"]["complete"])
            self.assertEqual(
                read_cursor(root)["pending"], ["history-2025", "history-2026"]
            )
            self.assertEqual(
                [row["start"] for row in client.calls],
                ["2025-01-01", "2026-01-01"],
            )

    def test_workflow_policy(self) -> None:
        corpus = (ROOT / ".github/workflows/corpus.yml").read_text(encoding="utf-8")
        legacy = (ROOT / ".github/workflows/archive.yml").read_text(encoding="utf-8")
        discover = (ROOT / ".github/workflows/discover.yml").read_text(encoding="utf-8")
        feed = (ROOT / ".github/workflows/feed.yml").read_text(encoding="utf-8")

        for required in (
            'cron: "17 04,10,16,22 * * *"',
            "group: arxiv-oai-corpus",
            "cancel-in-progress: false",
            "pipeline/corpusbatch.py",
            "PROMOTED_TAG: corpus-v2",
            "MIN_READY: 3145000",
            'if [ "$history_complete" = "true" ] &&',
            '[ "$paper_count" -ge "$MIN_READY" ] &&',
            '[ -n "$coverage_day" ]; then',
            'python pipeline/corpus.py check --root "$CORPUS_ROOT" --stage-only',
            'swap_asset "$PROMO_ROOT/index.json" index.json index',
            'swap_asset "$PROMO_ROOT/cloud-ready.json" cloud-ready.json ready',
            'pointer_name="pointer-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-${archive_digest:0:16}.json"',
            "awk -F '\\t' '$2 ~ /^pointer-",
            'event_type:"corpus-promoted"',
            "index_sha256:$index_sha256",
            "ready_sha256:$ready_sha256",
            "cloud-ready.json",
            "snapshot_complete:true",
            "coverage_through_year:$coverage_through_year",
            "coverage_through_day:$coverage_through_day",
            'echo "coverage_day=$coverage_day" >> "$GITHUB_OUTPUT"',
            "coverage_year=${coverage_day%%-*}",
            'echo "history_complete=$history_complete" >> "$GITHUB_OUTPUT"',
            "steps.snapshot.outputs.ready == 'true'",
            "steps.prep.outputs.changed == 'true'",
            "steps.prep.outputs.ready == 'true'",
            "actions/upload-artifact@v4",
            "stage_merge:",
            "needs: stage_merge",
            "inputs.mode != 'merge' || needs.stage_merge.result == 'success'",
            "name: corpus-source-${{ github.run_id }}",
            "actions/download-artifact@v4",
            'cp "$RUNNER_TEMP/corpus-source/corpus.tar.gz" "$CORPUS_FILE"',
            "([.parts[].name] | length == (unique | length))",
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
        self.assertIn('missing_assets+=("$PROMO_ROOT/$asset")', corpus)
        self.assertIn(
            'gh release upload "$PROMOTED_TAG" "${missing_assets[@]}"', corpus
        )
        self.assertNotIn(
            'gh release upload "$PROMOTED_TAG" "$PROMO_ROOT/$asset"', corpus
        )
        self.assertLess(
            corpus.index('gh release upload "$PROMOTED_TAG" "${missing_assets[@]}"'),
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
        for step in ("Prepare atomic promotion", "Validate promoted corpus"):
            start = corpus.index(f"- name: {step}")
            end = corpus.find("\n      - name:", start + 1)
            block = corpus[start : end if end >= 0 else len(corpus)]
            self.assertIn("steps.snapshot.outputs.ready == 'true'", block)
        for step in (
            "Publish promoted shards",
            "Verify promoted release",
            "Dispatch validated promotion",
        ):
            start = corpus.index(f"- name: {step}")
            end = corpus.find("\n      - name:", start + 1)
            block = corpus[start : end if end >= 0 else len(corpus)]
            self.assertIn("steps.prep.outputs.changed == 'true'", block)
            self.assertIn("steps.prep.outputs.ready == 'true'", block)
        self.assertLess(
            corpus.index('cmp "$PROMO_ROOT/cloud-ready.json"'),
            corpus.index("Dispatch validated promotion"),
        )
        self.assertLess(
            corpus.index("Dispatch validated promotion"),
            corpus.index("Acknowledge promotion"),
        )
        self.assertLess(
            corpus.index("Bound prior assets"),
            corpus.index("Publish promoted shards"),
        )
        self.assertLess(
            corpus.index("Dispatch validated promotion"),
            corpus.index("Bound promoted assets"),
        )
        self.assertEqual(corpus.count("pipeline/reap.py promo"), 2)
        self.assertEqual(corpus.count("pipeline/reap.py point"), 2)
        self.assertNotIn("Retire stale shard assets", corpus)
        self.assertNotIn("corpus-keep.txt", corpus)
        self.assertNotIn("schedule:", legacy)
        self.assertIn("group: arxiv-oai-corpus", legacy)
        self.assertIn("if: vars.ATLAS_LEGACY == 'true'", legacy)
        self.assertIn("group: arxiv-daily-feed", feed)
        self.assertNotIn("group: arxiv-oai-corpus", feed)
        self.assertIn("retention-days: 1", corpus)
        self.assertLess(
            corpus.index("Assemble immutable merge source"),
            corpus.index("Download staged merge source"),
        )
        self.assertLess(
            corpus.index("Download staged merge source"),
            corpus.index("Restore release checkpoint"),
        )
        self.assertIn('default: "corpus-v2"', discover)

        sweep = (ROOT / ".github/workflows/sweep.yml").read_text(encoding="utf-8")
        self.assertIn(
            'echo "SWEEP_ROOT=$RUNNER_TEMP/sweep/arxiv-sweep"',
            sweep,
        )
        self.assertEqual(sweep.count("--start-year 2005"), 2)
        self.assertEqual(sweep.count("--end-year 2018"), 2)
        self.assertIn("split -b 450m", sweep)
        self.assertIn("gh workflow run corpus.yml", sweep)
        self.assertIn("-f mode=merge", sweep)
        self.assertNotIn("pipeline/corpus.py merge", sweep)
        self.assertNotIn('event_type:"corpus-promoted"', sweep)
        self.assertGreaterEqual(sweep.count("set -o pipefail"), 2)
        self.assertGreaterEqual(corpus.count("set -o pipefail"), 3)
        self.assertLess(
            sweep.index("Attach sealed sweep"),
            sweep.index("Package canonical checkpoint"),
        )
        self.assertLess(
            sweep.index("Package canonical checkpoint"),
            sweep.index("Publish canonical checkpoint"),
        )
        self.assertLess(
            sweep.index("Publish canonical checkpoint"),
            sweep.index("Dispatch consolidation"),
        )
        self.assertEqual(sweep.count("pipeline/reap.py promo"), 0)
        self.assertEqual(sweep.count("pipeline/reap.py point"), 2)

    def test_phase_chain(self) -> None:
        corpus = (ROOT / ".github/workflows/corpus.yml").read_text(encoding="utf-8")
        chain = corpus[
            corpus.index("- name: Continue pipeline") : corpus.index(
                "- name: Enforce harvest result"
            )
        ]

        for guard in (
            "steps.harvest.outcome == 'success'",
            "steps.checkpoint.outcome == 'success'",
            "steps.merge.outcome == 'success'",
            "steps.snapshot.outcome == 'success'",
            "steps.package.outcome == 'success'",
            "steps.checkpoint_release.outcome == 'success'",
            "steps.snapshot.outputs.ready == 'false'",
            "steps.verify_promo.outcome == 'success'",
            "steps.merge.outputs.promote == 'false'",
            "steps.merge.outputs.history_complete == 'false'",
            "steps.merge.outputs.history_complete == 'true'",
            "steps.prep.outcome == 'success'",
            "steps.acknowledge.outcome == 'success'",
            ".prior_page_count",
            ".page_count > .prior_page_count",
            '.reason == "sealed"',
            '.reason == "page-limit"',
            '.reason == "time-limit"',
            "RUN_MODE: ${{ inputs.mode || 'harvest' }}",
            'if [ "$RUN_MODE" = "merge" ]',
            "next_mode=harvest",
            "next_mode=merge",
            ".history.complete == true",
            ".active.generation == $result[0].generation",
            "if ! jq -e",
            "safely checkpointed",
            "gh workflow run corpus.yml",
            '-f mode="$next_mode"',
            '-f pages="$CHAIN_PAGES"',
            '-f minutes="$CHAIN_MINUTES"',
        ):
            self.assertIn(guard, chain)
        self.assertNotIn('.reason == "token-expiring"', chain)
        self.assertIn('CHAIN_PAGES: "5000"', chain)
        self.assertIn('CHAIN_MINUTES: "180"', chain)
        self.assertNotIn("inputs.pages", chain)
        self.assertNotIn("inputs.minutes", chain)
        self.assertIn("actions: write", corpus)
        self.assertLess(
            corpus.index("- name: Publish release checkpoint"),
            corpus.index("- name: Continue pipeline"),
        )
        self.assertIn("if: inputs.mode != 'merge'", corpus)
        self.assertIn("MAX_MINUTES: ${{ inputs.minutes || '180' }}", corpus)

    def test_phase_isolation(self) -> None:
        corpus = (ROOT / ".github/workflows/corpus.yml").read_text(encoding="utf-8")

        def step(name: str) -> str:
            start = corpus.index(f"- name: {name}")
            end = corpus.find("\n      - name:", start + 1)
            return corpus[start : end if end >= 0 else len(corpus)]

        harvest = step("Harvest official metadata")
        merge = step("Merge sealed generations")
        snapshot = step("Assess snapshot readiness")
        package = step("Package checkpoint")
        release = step("Publish release checkpoint")

        self.assertIn("if: inputs.mode != 'merge'", harvest)
        self.assertNotIn("pipeline/corpus.py merge", harvest)
        self.assertIn("inputs.mode == 'merge'", merge)
        self.assertIn("steps.checkpoint.outcome == 'success'", merge)
        self.assertIn("steps.merge.outcome == 'success'", snapshot)
        self.assertIn("!cancelled() && steps.checkpoint.outcome == 'success'", package)
        self.assertIn("!cancelled() && steps.package.outcome == 'success'", release)
        self.assertLess(
            corpus.index("Harvest official metadata"),
            corpus.index("Package checkpoint"),
        )
        self.assertLess(
            corpus.index("Package checkpoint"), corpus.index("Continue pipeline")
        )

    def test_phase_budget(self) -> None:
        import re

        corpus = (ROOT / ".github/workflows/corpus.yml").read_text(encoding="utf-8")
        timeout = re.findall(r"^    timeout-minutes: (\d+)$", corpus, re.MULTILINE)
        dispatch = re.search(
            r'minutes:\n(?:        .*\n){2}        default: "(\d+)"', corpus
        )
        runtime = re.search(
            r"MAX_MINUTES: \$\{\{ inputs\.minutes \|\| '(\d+)' \}\}", corpus
        )
        chain = re.search(r'CHAIN_MINUTES: "(\d+)"', corpus)

        self.assertEqual(len(timeout), 1)
        self.assertIsNotNone(dispatch)
        self.assertIsNotNone(runtime)
        self.assertIsNotNone(chain)
        job_minutes = int(timeout[0])
        phase_minutes = {
            int(dispatch.group(1)),
            int(runtime.group(1)),
            int(chain.group(1)),
        }
        self.assertEqual(len(phase_minutes), 1)
        harvest_minutes = phase_minutes.pop()
        self.assertGreater(harvest_minutes, 0)
        self.assertGreaterEqual(job_minutes, harvest_minutes * 2)

        chain_block = corpus[
            corpus.index("- name: Continue pipeline") : corpus.index(
                "- name: Enforce harvest result"
            )
        ]
        self.assertEqual(
            chain_block.count(
                "if jq -e '.history.complete == true' "
                '"$CORPUS_ROOT/cursor.json" >/dev/null; then'
            ),
            2,
        )
        self.assertNotIn(".pending | length", chain_block)

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
            self.assertEqual(cursor["coverage_through_day"], "2005-12-31")
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
            self.assertEqual(
                read_cursor(root)["coverage_through_day"],
                "2026-08-28",
            )

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

    def test_stage_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir(parents=True)
            (archive / "index.json").write_text("{}")

            report = check_root(root, archive=False)

            self.assertIsNone(report["archive"])
            with self.assertRaises(ValueError):
                check_root(root)

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
        unsafe = full_paper("2608.00001")
        unsafe["abstract"] = (
            "Draft at https://www.overleaf.com/project/"
            "5e2b14694c5dc600017292e6 or email author@example.org "
            "before release."
        )
        unsafe["authors"] = ["Ada <ada@example.org>"]
        final = TestPage((unsafe,), None, "2026-08-27T00:17:00Z")
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
            pack_root(source, checkpoint)

            with tarfile.open(checkpoint, "r:gz") as bundle:
                members = [
                    bundle.extractfile(member).read()
                    for member in bundle.getmembers()
                    if member.isfile() and member.name.endswith(".json.gz")
                ]
            public = b"".join(gzip.decompress(content) for content in members)
            self.assertNotIn(b"example.org", public)
            self.assertNotIn(b"overleaf.com/project", public)

            unpack_root(checkpoint, restored)
            plan = prep_release(restored / "archive", output)

            paper = read_shard(output / plan["assets"][0])["papers"][0]
            self.assertEqual(paper["abstract"], "Draft at or email before release.")
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

            seed_cursor(root, "2026-08-27T00:17:00Z")
            path = root / "cursor.json"
            cursor = json.loads(path.read_text(encoding="utf-8"))
            cursor["coverage_through_day"] = "2026-02-31"
            path.write_text(json.dumps(cursor), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coverage day"):
                read_cursor(root)


if __name__ == "__main__":
    unittest.main()
