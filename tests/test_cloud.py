import gzip
import hashlib
import json
import struct
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from archive import add_day, migrate_archive, write_manifest
from cloud import (
    MAGIC,
    ROUTE_COUNT,
    ROUTE_MAGIC,
    archive_text,
    build_cloud,
    validate_cloud,
)
from cloudvec import row_hash
from embed import EMBED_DIM, MODEL, MODEL_DIGEST
from omit import ids_hash
from rank import load_rules
from routes import load_anchors, load_node_ids, project_points


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")


def paper(identifier: str, category: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": f"Learning with {category}",
        "abstract": "We test a semantic learning method with controlled evidence.",
        "authors": ["Ada Researcher"],
        "categories": [category],
        "primary_category": category,
        "published": "2020-01-02T01:00:00Z",
        "updated": "2020-01-02T01:00:00Z",
        "comment": "",
    }


def intake(papers: list[dict]) -> dict:
    return {
        "source_total": len(papers),
        "fetched_count": len(papers),
        "unique_count": len(papers),
        "page_count": 1,
        "query": "submittedDate:[202001020000 TO 202001022359]",
        "papers": papers,
    }


def save_anchors(path: Path) -> np.ndarray:
    vectors = np.zeros((ROUTE_COUNT, EMBED_DIM), dtype=np.float32)
    for index in range(ROUTE_COUNT):
        vectors[index, index] = 1
    points = np.asarray(
        [[index * 10, index * 5, index] for index in range(ROUTE_COUNT)],
        dtype=np.float32,
    )
    np.savez_compressed(
        path,
        schema_version=1,
        model=MODEL,
        model_digest=MODEL_DIGEST,
        dimensions=EMBED_DIM,
        ids=np.asarray([f"anchor:{index}" for index in range(ROUTE_COUNT)]),
        vectors=vectors,
        points=points,
    )
    return vectors


class CloudTests(unittest.TestCase):
    def test_route_ties(self) -> None:
        vectors = np.zeros((1, EMBED_DIM), dtype=np.float32)
        vectors[0, 0] = 1
        anchors = np.zeros((10, EMBED_DIM), dtype=np.float32)
        anchors[:, 1] = 1
        points = np.asarray([[index, 0, 0] for index in range(10)], dtype=np.float32)

        _projected, indexes, scores = project_points(vectors, anchors, points)

        self.assertEqual(indexes[0].tolist(), list(range(ROUTE_COUNT)))
        self.assertEqual(scores[0].tolist(), [32768] * ROUTE_COUNT)

    def test_anchor_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            papers = data / "papers"
            papers.mkdir(parents=True)
            paper_bundle = {
                "schema_version": 1,
                "papers": [{} for _ in range(4)],
                "layout": {
                    "positions": {f"paper:{index}": [index, 0, 0] for index in range(4)}
                },
            }
            content = json.dumps(paper_bundle).encode()
            digest = hashlib.sha256(content).hexdigest()
            (papers / f"{digest}.json").write_bytes(content)
            core = {
                "layout": {
                    "node_count": 8,
                    "positions": {
                        f"anchor:{index}": [index, 1, 0] for index in range(4)
                    },
                },
                "paper_asset": {
                    "schema_version": 1,
                    "path": f"/data/papers/{digest}.json",
                    "sha256": digest,
                    "bytes": len(content),
                    "paper_count": 4,
                },
            }
            atlas = data / "atlas.json"
            atlas.write_text(json.dumps(core), encoding="utf-8")

            self.assertEqual(
                load_node_ids(atlas),
                {f"anchor:{index}" for index in range(4)}
                | {f"paper:{index}" for index in range(4)},
            )

            anchors = root / "anchors.npz"
            save_anchors(anchors)
            with self.assertRaisesRegex(RuntimeError, "do not match"):
                load_anchors(anchors, load_node_ids(atlas) - {"anchor:7"})

            core["paper_asset"]["bytes"] += 1
            atlas.write_text(json.dumps(core), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "identities are invalid"):
                load_node_ids(atlas)

    def test_workflow_policy(self) -> None:
        workflow = (ROOT / ".github/workflows/cloud.yml").read_text(encoding="utf-8")

        for required in (
            "tag=corpus-v1",
            "workflow_dispatch:",
            "gh release view corpus-v2",
            "corpus-v2 owns the published cloud",
            "(-[0-9a-f]{16})?",
            "actions/cache/restore@v4",
            "actions/cache/save@v4",
            "python pipeline/cloud.py --check",
            "git add web/public/data/cloud",
            "git pull --rebase origin main",
            "git push origin HEAD:main",
            "gh workflow run deploy.yml --ref main",
            "points.sha256",
            "meta.sha256",
            "routes.sha256",
            "migrate_archive(root)",
            "write_manifest(root)",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("repository_dispatch:", "workflow_run:", "schedule:"):
            self.assertNotIn(forbidden, workflow)
        self.assertLess(
            workflow.index("python pipeline/cloud.py --check"),
            workflow.index("git add web/public/data/cloud"),
        )

    def test_semantic_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cache = root / "cache"
            output = root / "cloud"
            anchors = root / "anchors.npz"
            source = [paper("2001.00001", "cs.LG"), paper("2001.00002", "math.AT")]
            add_day(archive, date(2020, 1, 2), intake(source), RULES)
            vectors = save_anchors(anchors)
            payload = json.loads(
                gzip.decompress((archive / "2020-01.json.gz").read_bytes())
            )
            rows = [(item["id"], archive_text(item)) for item in payload["papers"]]
            cache.mkdir()
            np.savez_compressed(
                cache / "2020-01.npz",
                ids=np.asarray([identifier for identifier, _ in rows]),
                hashes=np.asarray([row_hash(*row) for row in rows]),
                vectors=vectors[:2],
                done=np.ones(2, dtype=bool),
            )

            manifest = build_cloud(archive, anchors, cache, output, 2)
            content = (output / "2020-01.bin").read_bytes()
            magic, count = struct.unpack("<8sI", content[:12])
            points = np.frombuffer(content[12 : 12 + count * 12], dtype="<f4").reshape(
                count, 3
            )
            metadata = json.loads((output / "2020-01.json").read_text())
            routes = (output / "2020-01.routes").read_bytes()
            route_head = struct.unpack("<8sIHH32s32s", routes[:80])

            self.assertEqual(magic, MAGIC)
            self.assertEqual(count, 2)
            self.assertEqual(len(content), 12 + count * 13)
            self.assertTrue(np.isfinite(points).all())
            self.assertEqual(manifest["count"], 2)
            self.assertEqual(metadata["count"], 2)
            self.assertEqual(metadata["papers"][0][0], "2001.00001")
            self.assertEqual(route_head[:4], (ROUTE_MAGIC, 2, ROUTE_COUNT, ROUTE_COUNT))
            self.assertEqual(len(routes), 80 + 2 * ROUTE_COUNT * 4)
            pairs = np.frombuffer(routes[80:], dtype="<u2").reshape(2, ROUTE_COUNT, 2)
            self.assertEqual(pairs[0, 0].tolist(), [0, 65535])
            self.assertEqual(pairs[1, 0].tolist(), [1, 65535])
            self.assertEqual(validate_cloud(archive, output), manifest)

            repeated = build_cloud(archive, anchors, cache, output, 2)
            self.assertEqual(repeated, manifest)

            polluted = {
                **manifest,
                "shards": [
                    *manifest["shards"],
                    manifest["shards"][0] | {"month": "1999-01"},
                ],
            }
            (output / "index.json").write_text(json.dumps(polluted), encoding="utf-8")
            cleaned = build_cloud(archive, anchors, cache, output, 2)
            self.assertEqual([row["month"] for row in cleaned["shards"]], ["2020-01"])

            bad_routes = bytearray(routes)
            struct.pack_into("<H", bad_routes, 80, ROUTE_COUNT)
            route_path = output / "2020-01.routes"
            route_path.write_bytes(bad_routes)
            corrupted = json.loads(json.dumps(cleaned))
            corrupted["shards"][0]["routes"] = {
                "path": route_path.name,
                "sha256": hashlib.sha256(bad_routes).hexdigest(),
                "bytes": len(bad_routes),
            }
            (output / "index.json").write_text(json.dumps(corrupted), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "route contract drifted"):
                validate_cloud(archive, output)

            route_path.write_bytes(routes)
            (output / "index.json").write_text(json.dumps(cleaned), encoding="utf-8")
            (output / "2020-01.bin").write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "points drifted"):
                validate_cloud(archive, output)

    def test_anchor_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cache = root / "cache"
            output = root / "cloud"
            anchors = root / "anchors.npz"
            source = [paper("2001.00001", "cs.LG")]
            add_day(archive, date(2020, 1, 2), intake(source), RULES)
            vectors = save_anchors(anchors)
            payload = json.loads(
                gzip.decompress((archive / "2020-01.json.gz").read_bytes())
            )
            rows = [(item["id"], archive_text(item)) for item in payload["papers"]]
            cache.mkdir()
            np.savez(
                cache / "2020-01.npz",
                ids=np.asarray([row[0] for row in rows]),
                hashes=np.asarray([row_hash(*row) for row in rows]),
                vectors=vectors[:1],
                done=np.ones(1, dtype=bool),
            )
            first = build_cloud(archive, anchors, cache, output, 1)
            with np.load(anchors) as bundle:
                changed = {key: bundle[key] for key in bundle.files}
            changed["points"] = np.asarray(changed["points"]) + 1
            np.savez_compressed(anchors, **changed)

            second = build_cloud(archive, anchors, cache, output, 1)

            self.assertNotEqual(first["anchor_sha256"], second["anchor_sha256"])
            self.assertEqual(
                second["anchor_sha256"],
                second["shards"][0]["anchor_sha256"],
            )
            self.assertEqual(validate_cloud(archive, output), second)

    def test_legacy_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            add_day(
                archive,
                date(2020, 1, 2),
                intake([paper("2001.00001", "cs.LG")]),
                RULES,
            )
            path = archive / "2020-01.json.gz"
            payload = json.loads(gzip.decompress(path.read_bytes()))
            payload["papers"][0]["comment"] = "legacy"
            path.write_bytes(gzip.compress(json.dumps(payload).encode(), mtime=0))

            self.assertEqual(migrate_archive(archive), ["2020-01"])
            first = write_manifest(archive)
            normalized = json.loads(gzip.decompress(path.read_bytes()))
            self.assertNotIn("comment", normalized["papers"][0])
            self.assertEqual(migrate_archive(archive), [])
            self.assertEqual(write_manifest(archive), first)

    def test_foreground_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"
            cache = root / "cache"
            output = root / "cloud"
            anchors = root / "anchors.npz"
            source = [paper("2001.00001", "cs.LG"), paper("2001.00002", "math.AT")]
            add_day(archive, date(2020, 1, 2), intake(source), RULES)
            vectors = save_anchors(anchors)
            payload = json.loads(
                gzip.decompress((archive / "2020-01.json.gz").read_bytes())
            )
            rows = [(item["id"], archive_text(item)) for item in payload["papers"]]
            cache.mkdir()
            np.savez_compressed(
                cache / "2020-01.npz",
                ids=np.asarray([identifier for identifier, _ in rows]),
                hashes=np.asarray([row_hash(*row) for row in rows]),
                vectors=vectors[:2],
                done=np.ones(2, dtype=bool),
            )
            foreground = {"2020-01": {"2001.00001"}}
            baseline = build_cloud(archive, anchors, cache, output, 2)
            baseline_content = (output / "2020-01.bin").read_bytes()
            baseline_second = baseline_content[24:36]
            baseline_routes = (output / "2020-01.routes").read_bytes()
            baseline_second_route = baseline_routes[
                80 + ROUTE_COUNT * 4 : 80 + ROUTE_COUNT * 8
            ]

            manifest = build_cloud(
                archive, anchors, cache, output, 2, foreground=foreground
            )

            self.assertEqual(manifest["source_count"], 2)
            self.assertEqual(manifest["count"], 1)
            self.assertEqual(manifest["omitted_count"], 1)
            self.assertEqual(manifest["shards"][0]["omitted_ids"], ["2001.00001"])
            metadata = json.loads((output / "2020-01.json").read_text())
            self.assertEqual([row[0] for row in metadata["papers"]], ["2001.00002"])
            self.assertEqual(
                (output / "2020-01.bin").read_bytes()[12:24], baseline_second
            )
            self.assertEqual(
                (output / "2020-01.routes").read_bytes()[80:],
                baseline_second_route,
            )
            self.assertEqual(baseline["count"], 2)
            self.assertEqual(validate_cloud(archive, output, foreground), manifest)

            polluted = json.loads((output / "index.json").read_text())
            polluted["shards"][0]["omitted_ids"] = ["2001.00002"]
            polluted["shards"][0]["omitted_sha256"] = ids_hash(["2001.00002"])
            (output / "index.json").write_text(json.dumps(polluted))
            with self.assertRaisesRegex(RuntimeError, "omission proof"):
                validate_cloud(archive, output, foreground)


if __name__ == "__main__":
    unittest.main()
