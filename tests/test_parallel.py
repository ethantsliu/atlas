from __future__ import annotations

import gzip
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from archive import add_day  # noqa: E402
from cloud import (  # noqa: E402
    ROUTE_COUNT,
    archive_text,
    build_cloud,
)
from cloudvec import load_cache, row_hash  # noqa: E402
from embed import EMBED_DIM, MODEL, MODEL_DIGEST  # noqa: E402
from parallel import build_part, join_parts, make_plan  # noqa: E402
from rank import load_rules  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")


def paper(identifier: str, day: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A semantic learning paper",
        "abstract": "We test controlled semantic evidence.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": f"{day}T01:00:00Z",
        "updated": f"{day}T01:00:00Z",
        "comment": "",
    }


def intake(rows: list[dict], day: str) -> dict:
    stamp = day.replace("-", "")
    return {
        "source_total": len(rows),
        "fetched_count": len(rows),
        "unique_count": len(rows),
        "page_count": 1,
        "query": f"submittedDate:[{stamp}0000 TO {stamp}2359]",
        "papers": rows,
    }


def save_anchors(path: Path) -> np.ndarray:
    vectors = np.zeros((ROUTE_COUNT, EMBED_DIM), dtype=np.float32)
    for index in range(ROUTE_COUNT):
        vectors[index, index] = 1
    np.savez_compressed(
        path,
        schema_version=1,
        model=MODEL,
        model_digest=MODEL_DIGEST,
        dimensions=EMBED_DIM,
        ids=np.asarray([f"anchor:{index}" for index in range(ROUTE_COUNT)]),
        vectors=vectors,
        points=np.asarray(
            [[index * 10, index * 5, index] for index in range(ROUTE_COUNT)],
            dtype=np.float32,
        ),
    )
    return vectors


def seed_cache(archive: Path, cache: Path, month: str, vectors: np.ndarray) -> None:
    payload = json.loads(gzip.decompress((archive / f"{month}.json.gz").read_bytes()))
    rows = [(row["id"], archive_text(row)) for row in payload["papers"]]
    cache.mkdir(parents=True, exist_ok=True)
    np.savez(
        cache / f"{month}.npz",
        ids=np.asarray([identifier for identifier, _ in rows]),
        hashes=np.asarray([row_hash(*row) for row in rows]),
        vectors=vectors[: len(rows)],
        done=np.ones(len(rows), dtype=bool),
    )


class ParallelTests(unittest.TestCase):
    def test_workflow(self) -> None:
        workflow = (ROOT / ".github/workflows/cloudall.yml").read_text()
        serial = (ROOT / ".github/workflows/cloud.yml").read_text()

        for required in (
            'cron: "47 11 * * *"',
            "github.event_name == 'schedule'",
            "max-parallel: 16",
            "fail-fast: false",
            "contents: read",
            "contents: write",
            "cloud-all only accepts the corpus-v2 release",
            "cloud-ready.json",
            "DISPATCH_INDEX",
            "DISPATCH_READY",
            "Corpus dispatch must bind immutable index and readiness digests",
            'index_name="index-${DISPATCH_INDEX:0:16}.json"',
            'ready_name="ready-${DISPATCH_READY:0:16}.json"',
            'if [ -n "$DISPATCH_INDEX" ] && [ "$index_sha" != "$DISPATCH_INDEX" ]',
            'if [ -n "$DISPATCH_READY" ] && [ "$ready_sha" != "$DISPATCH_READY" ]',
            "base: ${{ steps.plan.outputs.base }}",
            'echo "base=$(git rev-parse HEAD)"',
            "ref: ${{ needs.plan.outputs.base }}",
            ".history_complete == true",
            "MIN_CLOUD: 1000000",
            '"$paper_count" -lt "$MIN_CLOUD"',
            "daily cloud reconciliation has no work",
            ".index_sha256 == $index_sha256",
            ".paper_count == $paper_count",
            "month must have exactly one source row",
            "^[0-9]{4}-(0[1-9]|1[0-2])$",
            "^${month}(-[0-9a-f]{16})?\\.json\\.gz$",
            "^[0-9a-f]{64}$",
            "python pipeline/parallel.py plan",
            "python pipeline/parallel.py build",
            "python pipeline/parallel.py join",
            "--atlas web/public/data/atlas.json",
            "--anchors data/source/anchors.npz",
            "--prior web/public/data/cloud",
            "actions/cache/save@v4",
            "cloud-part-${{ runner.os }}-${{ matrix.part }}-",
            "github.run_attempt",
            "pattern: cloud-part-*",
            "merge-multiple: true",
            "needs: [plan, points]",
            "overwrite: true",
            "timeout-minutes: 180",
            "base_sha=$(git rev-parse HEAD)",
            "git fetch origin main",
            'if [ "$remote_sha" != "$base_sha" ]',
            "restart cloud-all",
            "actions: write",
        ):
            self.assertIn(required, workflow)
        self.assertLess(
            workflow.index("python pipeline/parallel.py join"),
            workflow.index("git add web/public/data/cloud"),
        )
        self.assertEqual(
            workflow.count("ref: ${{ needs.plan.outputs.base }}"),
            2,
        )
        self.assertLess(
            workflow.index('echo "base=$(git rev-parse HEAD)"'),
            workflow.index("ref: ${{ needs.plan.outputs.base }}"),
        )
        self.assertIn("gh release view corpus-v2", serial)
        self.assertNotIn("--allow-shrink", workflow)
        self.assertNotIn("git pull --rebase", workflow)
        self.assertNotIn("gh workflow run deploy.yml", workflow)
        self.assertEqual(workflow.count("gh workflow run check.yml"), 1)
        self.assertLess(
            workflow.index("git push origin HEAD:main"),
            workflow.index("gh workflow run check.yml"),
        )
        self.assertNotIn("repository_dispatch:", serial)
        self.assertNotIn("workflow_run:", serial)
        self.assertNotIn("schedule:", serial)

    def test_cross_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2020-01.npz"
            records = [("2001.00001", "new text"), ("2001.00002", "same text")]
            hashes = np.asarray([row_hash(*row) for row in records])
            saved = np.ones((2, EMBED_DIM), dtype=np.float32)
            np.savez(
                path,
                ids=np.asarray([row[0] for row in records]),
                hashes=np.asarray([row_hash(records[0][0], "old text"), hashes[1]]),
                vectors=saved,
                done=np.ones(2, dtype=bool),
            )

            vectors, done = load_cache(path, records, hashes)

        self.assertEqual(done.tolist(), [False, True])
        self.assertTrue(np.array_equal(vectors[0], np.zeros(EMBED_DIM)))
        self.assertTrue(np.array_equal(vectors[1], saved[1]))

    def test_atomic_join(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cloud = root / "cloud"
            anchors = root / "anchors.npz"
            rows = [paper("2001.00001", "2020-01-02")]
            add_day(archive, date(2020, 1, 2), intake(rows, "2020-01-02"), RULES)
            rows = [paper("2002.00001", "2020-02-02")]
            add_day(archive, date(2020, 2, 2), intake(rows, "2020-02-02"), RULES)
            vectors = save_anchors(anchors)
            plan = make_plan(archive, cloud, 2, anchors=anchors)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            parts = root / "parts"
            for part in plan["partitions"]:
                output = root / f"worker-{part['id']}"
                cache = root / f"cache-{part['id']}"
                month = part["months"][0]
                seed_cache(archive, cache, month, vectors[:1])
                build_part(
                    archive, anchors, cache, output, plan_path, part["id"], 2, "native"
                )
                parts.mkdir(exist_ok=True)
                for path in output.iterdir():
                    shutil.copyfile(path, parts / path.name)

            manifest = join_parts(archive, cloud, plan_path, parts, anchors=anchors)

            self.assertEqual(manifest["count"], 2)
            self.assertEqual(
                [row["month"] for row in manifest["shards"]], ["2020-01", "2020-02"]
            )
            equal_plan = make_plan(archive, cloud, 16, anchors=anchors)
            equal_path = root / "equal.json"
            equal_path.write_text(json.dumps(equal_plan), encoding="utf-8")
            empty_parts = root / "empty-parts"
            empty_parts.mkdir()
            self.assertEqual(
                join_parts(archive, cloud, equal_path, empty_parts, anchors=anchors)[
                    "source_count"
                ],
                2,
            )

            smaller = root / "smaller"
            add_day(
                smaller,
                date(2020, 1, 2),
                intake([paper("2001.00001", "2020-01-02")], "2020-01-02"),
                RULES,
            )
            smaller_plan = make_plan(smaller, cloud, 16, anchors=anchors)
            smaller_path = root / "smaller.json"
            smaller_path.write_text(json.dumps(smaller_plan), encoding="utf-8")
            before = {path.name: path.read_bytes() for path in cloud.iterdir()}
            with self.assertRaisesRegex(ValueError, "Cloud source regression"):
                join_parts(smaller, cloud, smaller_path, empty_parts, anchors=anchors)
            self.assertEqual(
                {path.name: path.read_bytes() for path in cloud.iterdir()}, before
            )
            migrated = join_parts(
                smaller,
                cloud,
                smaller_path,
                empty_parts,
                allow_shrink=True,
                anchors=anchors,
            )
            self.assertEqual(migrated["source_count"], 1)

            repeated = make_plan(archive, cloud, 16, anchors=anchors)
            self.assertEqual(repeated["changed_count"], 1)
            (cloud / "index.json").write_text("{}", encoding="utf-8")
            recovery = make_plan(archive, cloud, 16, anchors=anchors)
            self.assertEqual(recovery["changed_count"], 2)

    def test_missing_part(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cloud = root / "cloud"
            add_day(
                archive,
                date(2020, 1, 2),
                intake([paper("2001.00001", "2020-01-02")], "2020-01-02"),
                RULES,
            )
            plan = make_plan(archive, cloud, 16)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "fragments are missing"):
                join_parts(archive, cloud, plan_path, root / "parts")

    def test_stage_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cloud = root / "cloud"
            anchors = root / "anchors.npz"
            add_day(
                archive,
                date(2020, 1, 2),
                intake([paper("2001.00001", "2020-01-02")], "2020-01-02"),
                RULES,
            )
            vectors = save_anchors(anchors)
            plan = make_plan(archive, cloud, 1, anchors=anchors)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            cache = root / "cache"
            seed_cache(archive, cache, "2020-01", vectors[:1])
            parts = root / "parts"
            fragment = build_part(
                archive, anchors, cache, parts, plan_path, 0, 2, "native"
            )
            (parts / fragment["shards"][0]["meta"]["path"]).write_bytes(b"drift")
            cloud.mkdir()
            (cloud / "index.json").write_text("{}", encoding="utf-8")
            (cloud / "keep.bin").write_bytes(b"old")
            before = {path.name: path.read_bytes() for path in sorted(cloud.iterdir())}

            with self.assertRaisesRegex(ValueError, "asset drifted"):
                join_parts(archive, cloud, plan_path, parts, anchors=anchors)

            after = {path.name: path.read_bytes() for path in sorted(cloud.iterdir())}
            self.assertEqual(after, before)

    def test_dedupe_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cloud = root / "cloud"
            anchors = root / "anchors.npz"
            rows = [
                paper("2001.00001", "2020-01-02"),
                paper("2001.00002", "2020-01-02"),
            ]
            add_day(archive, date(2020, 1, 2), intake(rows, "2020-01-02"), RULES)
            vectors = save_anchors(anchors)
            foreground = {"2020-01": {"2001.00001"}}
            cache = root / "cache"
            seed_cache(archive, cache, "2020-01", vectors)
            build_cloud(archive, anchors, cache, cloud, 2)
            baseline = (cloud / "2020-01.bin").read_bytes()[24:36]
            plan = make_plan(archive, cloud, 1, foreground, anchors)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            parts = root / "parts"
            fragment = build_part(
                archive, anchors, cache, parts, plan_path, 0, 2, "native", cloud
            )

            manifest = join_parts(archive, cloud, plan_path, parts, anchors=anchors)

            self.assertEqual(manifest["source_count"], 2)
            self.assertEqual(manifest["count"], 1)
            self.assertEqual(manifest["omitted_count"], 1)
            metadata = json.loads((cloud / "2020-01.json").read_text())
            self.assertEqual([row[0] for row in metadata["papers"]], ["2001.00002"])
            self.assertEqual((cloud / "2020-01.bin").read_bytes()[12:24], baseline)

            fragment["shards"][0]["omitted_count"] = 0
            (parts / "part-00.json").write_text(json.dumps(fragment), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "omission proof"):
                join_parts(
                    archive,
                    root / "bad-cloud",
                    plan_path,
                    parts,
                    anchors=anchors,
                )

    def test_balance(self) -> None:
        source = {
            "schema_version": 1,
            "counts": {"all": 10, "likely": 10, "possible": 0, "outside": 0},
            "shards": [
                {
                    "month": f"2020-0{index}",
                    "path": f"2020-0{index}.json.gz",
                    "sha256": f"{index}" * 64,
                    "counts": {
                        "all": count,
                        "likely": count,
                        "possible": 0,
                        "outside": 0,
                    },
                }
                for index, count in enumerate((4, 3, 2, 1), start=1)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            (archive / "index.json").write_text(json.dumps(source), encoding="utf-8")

            plan = make_plan(archive, root / "cloud", 2)

        self.assertEqual([part["count"] for part in plan["partitions"]], [5, 5])

    def test_manifest_guard(self) -> None:
        source = {
            "schema_version": 1,
            "counts": {"all": 1, "likely": 1, "possible": 0, "outside": 0},
            "shards": [
                {
                    "month": "2020-01",
                    "path": "2020-02.json.gz",
                    "sha256": "a" * 64,
                    "counts": {
                        "all": 1,
                        "likely": 1,
                        "possible": 0,
                        "outside": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            archive.mkdir()
            index = archive / "index.json"
            index.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source shard"):
                make_plan(archive, root / "cloud", 1)
            source["shards"][0]["month"] = "2020-13"
            source["shards"][0]["path"] = "2020-13.json.gz"
            index.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source shard"):
                make_plan(archive, root / "cloud", 1)
            source["shards"][0]["month"] = "2020-01"
            source["shards"][0]["path"] = "2020-01.json.gz"
            source["counts"]["all"] = 2
            index.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not reconciled"):
                make_plan(archive, root / "cloud", 1)


if __name__ == "__main__":
    unittest.main()
