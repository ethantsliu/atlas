import gzip
import json
import struct
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from archive import add_day
from cloud import MAGIC, archive_text, build_cloud, row_hash
from embed import EMBED_DIM, MODEL, MODEL_DIGEST
from rank import load_rules


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
    vectors = np.zeros((2, EMBED_DIM), dtype=np.float32)
    vectors[0, 0] = 1
    vectors[1, 1] = 1
    points = np.asarray([[10, 0, 0], [0, 20, 0]], dtype=np.float32)
    np.savez_compressed(
        path,
        schema_version=1,
        model=MODEL,
        model_digest=MODEL_DIGEST,
        dimensions=EMBED_DIM,
        ids=np.asarray(["left", "right"]),
        vectors=vectors,
        points=points,
    )
    return vectors


class CloudTests(unittest.TestCase):
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
                vectors=vectors,
                done=np.ones(2, dtype=bool),
            )

            manifest = build_cloud(archive, anchors, cache, output, 2)
            content = (output / "2020-01.bin").read_bytes()
            magic, count = struct.unpack("<8sI", content[:12])
            points = np.frombuffer(content[12 : 12 + count * 12], dtype="<f4").reshape(
                count, 3
            )
            metadata = json.loads((output / "2020-01.json").read_text())

            self.assertEqual(magic, MAGIC)
            self.assertEqual(count, 2)
            self.assertEqual(len(content), 12 + count * 13)
            self.assertTrue(np.isfinite(points).all())
            self.assertEqual(manifest["count"], 2)
            self.assertEqual(metadata["count"], 2)
            self.assertEqual(metadata["papers"][0][0], "2001.00001")

            repeated = build_cloud(archive, anchors, cache, output, 2)
            self.assertEqual(repeated, manifest)


if __name__ == "__main__":
    unittest.main()
