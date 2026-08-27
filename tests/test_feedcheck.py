import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import feedcheck
from feed import day_query, day_summary, make_day, raw_payload
from rank import load_rules


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")
DAY = date(2026, 8, 21)


def make_intake() -> dict:
    paper = {
        "id": "2608.00001",
        "url": "https://arxiv.org/abs/2608.00001",
        "title": "Learning environments",
        "abstract": "We introduce a reinforcement learning environment.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2026-08-21T00:00:00Z",
        "updated": "2026-08-21T00:00:00Z",
        "comment": "",
    }
    return {
        "source_total": 1,
        "fetched_count": 1,
        "unique_count": 1,
        "page_count": 1,
        "query": day_query(DAY),
        "papers": [paper],
    }


def write_feed(root: Path, complete: bool = True) -> tuple[Path, Path, Path]:
    generated = root / "generated"
    public = root / "public"
    dist = root / "web/dist/data/feed"
    payload = make_day(DAY, make_intake(), RULES, 1)
    payload["source"]["complete"] = complete
    text = json.dumps(payload, indent=2) + "\n"
    index = {
        "schema_version": 1,
        "generated_at": payload["generated_at"],
        "days": [day_summary(payload)],
    }
    index_text = json.dumps(index, indent=2) + "\n"
    for target in (generated, public, dist):
        target.mkdir(parents=True)
        (target / "2026-08-21.json").write_text(text, encoding="utf-8")
        (target / "index.json").write_text(index_text, encoding="utf-8")
    raw = generated / "raw"
    raw.mkdir()
    (raw / "2026-08-21.json.gz").write_bytes(raw_payload(DAY, make_intake()))
    return generated, public, dist


class FeedCheckTests(unittest.TestCase):
    def test_valid_feed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            roots = write_feed(Path(folder))
            with patch.multiple(
                feedcheck,
                FEED_ROOT=roots[0],
                PUBLIC_ROOT=roots[1],
                ROOT=Path(folder),
            ):
                feedcheck.validate_feed()

    def test_partial_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            roots = write_feed(Path(folder), complete=False)
            with patch.multiple(
                feedcheck,
                FEED_ROOT=roots[0],
                PUBLIC_ROOT=roots[1],
                ROOT=Path(folder),
            ):
                with self.assertRaisesRegex(RuntimeError, "Incomplete daily intake"):
                    feedcheck.validate_feed()

    def test_raw_email(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            roots = write_feed(Path(folder))
            raw_path = roots[0] / "raw/2026-08-21.json.gz"
            raw = json.loads(gzip.decompress(raw_path.read_bytes()))
            raw["papers"][0]["comment"] = "Contact author@example. edu"
            body = json.dumps(raw, separators=(",", ":")).encode()
            raw_path.write_bytes(gzip.compress(body, mtime=0))
            with patch.multiple(
                feedcheck,
                FEED_ROOT=roots[0],
                PUBLIC_ROOT=roots[1],
                ROOT=Path(folder),
            ):
                with self.assertRaisesRegex(RuntimeError, "Unsafe raw public paper"):
                    feedcheck.validate_feed()

    def test_author_shape(self) -> None:
        paper = make_intake()["papers"][0]
        paper["authors"] = ["Ada Researcher", None]

        with self.assertRaisesRegex(RuntimeError, "Invalid daily bibliography"):
            feedcheck.validate_paper(paper, DAY.isoformat())

    def test_comment_shape(self) -> None:
        for comment in (None, 1, {"email": "ada@example.edu"}, ["email"]):
            with self.subTest(comment=comment):
                paper = make_intake()["papers"][0]
                paper["comment"] = comment
                with self.assertRaisesRegex(RuntimeError, "Invalid daily bibliography"):
                    feedcheck.validate_paper(paper, DAY.isoformat())

    def test_unicode_email(self) -> None:
        comments = (
            "Contact ada＠example.edu",
            "Contact ada@example．edu",
            "Open ／Users／account／private",
            "See https：／／localhost／private",
            "Read file：／／／tmp／private",
        )
        for comment in comments:
            with self.subTest(comment=comment):
                paper = make_intake()["papers"][0]
                paper["comment"] = comment
                with self.assertRaisesRegex(RuntimeError, "Unsafe daily public paper"):
                    feedcheck.validate_paper(paper, DAY.isoformat())

    def test_raw_shape(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            roots = write_feed(Path(folder))
            raw_path = roots[0] / "raw/2026-08-21.json.gz"
            raw = json.loads(gzip.decompress(raw_path.read_bytes()))
            raw["papers"][0]["comment"] = {"email": "ada@example.edu"}
            body = json.dumps(raw, separators=(",", ":")).encode()
            raw_path.write_bytes(gzip.compress(body, mtime=0))
            payload = json.loads((roots[0] / "2026-08-21.json").read_text())

            with self.assertRaisesRegex(RuntimeError, "Invalid raw bibliography"):
                feedcheck.validate_raw(raw_path, payload)


if __name__ == "__main__":
    unittest.main()
