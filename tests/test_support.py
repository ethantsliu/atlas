from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import add_day  # noqa: E402
from rank import load_rules  # noqa: E402
from support import (  # noqa: E402
    build_bundle,
    bundle_bytes,
    content_digest,
    corpus_digest,
    make_row,
    validate_bundle,
)


RULES = load_rules(ROOT / "data/source/feed.json")


def paper(identifier: str = "2401.00001") -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A semantic atlas",
        "abstract": "We build and test an atlas.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2024-01-02T01:00:00Z",
        "updated": "2024-01-03T01:00:00Z",
        "comment": "",
    }


def intake(papers: list[dict]) -> dict:
    return {
        "source_total": len(papers),
        "fetched_count": len(papers),
        "unique_count": len(papers),
        "page_count": 1,
        "query": "submittedDate:[202401020000 TO 202401022359]",
        "papers": papers,
    }


def archive_fixture(root: Path, papers: list[dict]) -> tuple[dict, dict]:
    manifest = add_day(root, date(2024, 1, 2), intake(papers), RULES)
    shard = manifest["shards"][0]
    return manifest, shard


class SupportTests(unittest.TestCase):
    def test_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, shard = archive_fixture(root, [paper()])
            row = make_row(paper(), shard, 0)
            bundle = build_bundle([row], corpus_digest(manifest))

            self.assertEqual(row["canonical_id"], "arxiv:2401.00001")
            self.assertEqual(row["title"], "A semantic atlas")
            self.assertEqual(
                set(row), {"canonical_id", "title", "url", "published", "archive"}
            )
            self.assertIs(validate_bundle(bundle, archive_root=root), bundle)
            self.assertEqual(bundle["content_sha256"], content_digest(bundle))

    def test_legacy_id(self) -> None:
        source = paper("hep-th/9901001v2")
        source["published"] = "2024-01-02T01:00:00Z"
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }

        row = make_row(source, shard, 3)

        self.assertEqual(row["canonical_id"], "arxiv:hep-th/9901001")
        self.assertEqual(row["url"], "https://arxiv.org/abs/hep-th/9901001")

    def test_determinism(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        left = make_row(paper("2401.00002"), shard, 1)
        right = make_row(paper("2401.00001v3"), shard, 0)
        corpus = corpus_digest({"generation": 1, "shards": ["2024-01"]})

        first = build_bundle([left, right], corpus)
        second = build_bundle([right, left], corpus)

        self.assertEqual(first, second)
        self.assertEqual(bundle_bytes(first), bundle_bytes(second))
        parsed = json.loads(bundle_bytes(first))
        self.assertEqual(parsed["papers"][0]["canonical_id"], "arxiv:2401.00001")
        self.assertEqual(
            corpus_digest({"shards": ["2024-01"], "generation": 1}), corpus
        )

    def test_strict_shape(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        bundle = build_bundle(
            [make_row(paper(), shard, 0)],
            "b" * 64,
        )
        cases = []
        hidden_root = json.loads(json.dumps(bundle))
        hidden_root["generated_at"] = "today"
        cases.append(hidden_root)
        hidden_paper = json.loads(json.dumps(bundle))
        hidden_paper["papers"][0]["abstract"] = "private bulk text"
        hidden_paper["content_sha256"] = content_digest(hidden_paper)
        cases.append(hidden_paper)
        wrong_url = json.loads(json.dumps(bundle))
        wrong_url["papers"][0]["url"] = "https://example.com/paper"
        wrong_url["content_sha256"] = content_digest(wrong_url)
        cases.append(wrong_url)

        for value in cases:
            with self.subTest(keys=sorted(value)):
                with self.assertRaises(RuntimeError):
                    validate_bundle(value)

    def test_digest_drift(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        bundle = build_bundle([make_row(paper(), shard, 0)], "b" * 64)
        bundle["papers"][0]["title"] = "Changed"

        with self.assertRaisesRegex(RuntimeError, "content digest"):
            validate_bundle(bundle)
        with self.assertRaisesRegex(RuntimeError, "corpus generation"):
            fixed = {**bundle, "content_sha256": content_digest(bundle)}
            validate_bundle(fixed, expected_digest="c" * 64)

    def test_archive_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, shard = archive_fixture(root, [paper()])
            bundle = build_bundle(
                [make_row(paper(), shard, 0)],
                corpus_digest(manifest),
            )
            path = root / shard["path"]
            path.write_bytes(path.read_bytes() + b"drift")

            with self.assertRaisesRegex(RuntimeError, "archive digest"):
                validate_bundle(bundle, archive_root=root)

    def test_row_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = paper("2401.00001")
            second = paper("2401.00002")
            manifest, shard = archive_fixture(root, [first, second])
            bundle = build_bundle(
                [make_row(first, shard, 1)],
                corpus_digest(manifest),
            )

            with self.assertRaisesRegex(RuntimeError, "row drifted"):
                validate_bundle(bundle, archive_root=root)

    def test_duplicates(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        row = make_row(paper(), shard, 0)
        payload = {
            "schema_version": 1,
            "corpus_digest": "b" * 64,
            "papers": [row, row],
        }
        payload["content_sha256"] = content_digest(payload)

        with self.assertRaisesRegex(RuntimeError, "duplicated or unsorted"):
            validate_bundle(payload)

    def test_digest_format(self) -> None:
        digest = corpus_digest({"corpus": "all-history"})
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            digest, hashlib.sha256(b'{"corpus":"all-history"}').hexdigest()
        )

    def test_title_safety(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        unsafe = (
            "Read /Users/account/private notes",
            "Open file:///tmp/private.pdf",
            "Contact hidden@example.com",
            "Contact hidden＠example.com",
            "Follow @hiddenuser",
            "See https://twitter.com/hidden/status/1",
            "See https://github.com/hidden/private",
            "Internal private-repo results",
            "sample-overleaf notes",
            "private_repo results",
            "left\u202eright",
            "zero\u200bwidth",
            "escape\x1bcode",
        )

        for title in unsafe:
            source = {**paper(), "title": title}
            with self.subTest(title=repr(title)):
                with self.assertRaisesRegex(RuntimeError, "unsafe title"):
                    make_row(source, shard, 0)

    def test_title_boundary(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        accepted = make_row({**paper(), "title": "a" * 512}, shard, 0)
        self.assertEqual(len(accepted["title"]), 512)

        with self.assertRaisesRegex(RuntimeError, "invalid title"):
            make_row({**paper(), "title": "a" * 513}, shard, 0)

    def test_forged_title(self) -> None:
        shard = {
            "month": "2024-01",
            "path": "2024-01.json.gz",
            "sha256": "a" * 64,
        }
        bundle = build_bundle([make_row(paper(), shard, 0)], "b" * 64)
        bundle["papers"][0]["title"] = "file:///tmp/private.pdf"
        bundle["content_sha256"] = content_digest(bundle)

        with self.assertRaisesRegex(RuntimeError, "unsafe title"):
            validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
