from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import write_manifest, write_shard  # noqa: E402
from discover import build_artifact, check_artifact  # noqa: E402


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(identifier: str, title: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": title,
        "abstract": "We propose a sparse routing algorithm for controlled agents.",
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2024-01-02T00:00:00Z",
        "updated": "2024-01-03T00:00:00Z",
        "scope": "likely",
        "relevance": {
            "relevant": True,
            "score": 8.0,
            "lane": "core",
            "reasons": ["core ML category"],
            "strong_hits": [],
            "support_hits": [],
        },
        "interest": {"score": 4.0, "reasons": []},
        "topics": [route("agents")],
        "tricks": [route("routing-and-moe")],
    }


def shard() -> dict:
    papers = [
        paper("2401.00001", "A sparse routing algorithm for agents"),
        paper("2401.00002", "A sparse routing algorithm for agents"),
    ]
    return {
        "schema_version": 1,
        "policy_version": "fixture-1",
        "month": "2024-01",
        "days": [],
        "counts": {"all": 2, "likely": 2, "possible": 0, "outside": 0},
        "papers": papers,
    }


class DiscoverTests(unittest.TestCase):
    def test_policy(self) -> None:
        workflow = (ROOT / ".github/workflows/discover.yml").read_text(encoding="utf-8")

        required = (
            "repository_dispatch:",
            "types: [corpus-promoted]",
            "schedule:",
            "workflow_dispatch:",
            "contents: read",
            "cancel-in-progress: false",
            "EVENT_NAME: ${{ github.event_name }}",
            'default: "all"',
            'default: "corpus-v2"',
            'if [ "$EVENT_NAME" = "workflow_dispatch" ] && [ "$scope" = "latest" ]',
            'jq -r \'.shards[].month\' "$manifest" > "$requested"',
            '--archive "$ARCHIVE_ROOT"',
            "actions/upload-artifact@v4",
            "tests.test_candidate",
            "tests.test_scan",
            "tests.test_retrieve",
            "tests.test_safety",
            "tests.test_privacy",
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, workflow)
        forbidden = (
            "contents: write",
            "git push",
            "git commit",
            "gh release create",
            "${{ runner.temp }}",
            "DISPATCH_MONTHS",
            'tag="corpus-v1"',
        )
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, workflow)

    def test_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(build_artifact(Path(directory), 4))

    def test_provisional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)

            artifact = build_artifact(root, 4)

            self.assertIsNotNone(artifact)
            self.assertIs(check_artifact(artifact, root), artifact)
            self.assertFalse(artifact["review_gate"]["automatic_promotion"])
            self.assertEqual(
                artifact["review_gate"]["required_receipt"],
                "declared-human-review",
            )
            self.assertTrue(artifact["candidates"])
            self.assertTrue(artifact["trick_candidates"])
            self.assertEqual(
                set(artifact["related_work"]),
                {row["candidate_id"] for row in artifact["candidates"]},
            )
            self.assertEqual(
                {row["status"] for row in artifact["related_work"].values()},
                {"candidate_only"},
            )
            self.assertEqual(
                {row["review_status"] for row in artifact["candidates"]},
                {"unreviewed"},
            )

    def test_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            artifact = build_artifact(root, 4)
            artifact["candidates"][0]["review_status"] = "reviewed"

            with self.assertRaises(ValueError):
                check_artifact(artifact, root)

    def test_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            artifact = build_artifact(root, 4)

            changed = copy.deepcopy(artifact)
            changed["coverage"]["loaded_months"] = ["2024-02"]
            with self.assertRaisesRegex(ValueError, "coverage"):
                check_artifact(changed, root)

            changed = copy.deepcopy(artifact)
            changed["coverage"]["extra"] = True
            with self.assertRaisesRegex(ValueError, "coverage"):
                check_artifact(changed, root)

            with self.assertRaisesRegex(ValueError, "between 1 and 48"):
                build_artifact(root, 49)

    def test_trick_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            artifact = build_artifact(root, 4)
            changes = (
                ("id", "candidate-bad"),
                ("label", "changed candidate label"),
                ("signals", []),
                ("support_count", 999),
            )
            for field, value in changes:
                with self.subTest(field=field):
                    changed = copy.deepcopy(artifact)
                    changed["trick_candidates"][0][field] = value
                    with self.assertRaises(ValueError):
                        check_artifact(changed, root)

            changed = copy.deepcopy(artifact)
            changed["trick_candidates"][0]["sources"][0]["span"] = [0, 1]
            with self.assertRaises(ValueError):
                check_artifact(changed, root)

            changed = copy.deepcopy(artifact)
            changed["trick_candidates"].reverse()
            with self.assertRaises(ValueError):
                check_artifact(changed, root)

    def test_trick_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            artifact = build_artifact(root, 4)
            source = artifact["trick_candidates"][0]["sources"][-1]
            source["source_id"] = "arxiv:2401.99999"
            artifact["trick_candidates"][0]["sources"].sort(
                key=lambda row: (
                    row["source_id"],
                    row["field"],
                    *row["span"],
                    row["text"],
                )
            )

            with self.assertRaisesRegex(ValueError, "does not resolve"):
                check_artifact(artifact, root)

    def test_support_digest(self) -> None:
        with (
            tempfile.TemporaryDirectory() as first_dir,
            tempfile.TemporaryDirectory() as second_dir,
        ):
            first = Path(first_dir)
            second = Path(second_dir)
            first_rows = [
                paper("2401.00001", "First method"),
                paper("2401.00002", "Second method"),
            ]
            second_rows = [
                paper("2401.00003", "Third method"),
                paper("2401.00004", "Fourth method"),
            ]
            write_shard(first, {**shard(), "papers": first_rows})
            write_shard(second, {**shard(), "papers": second_rows})
            write_manifest(first)
            write_manifest(second)

            left = build_artifact(first, 1)["candidates"][0]
            right = build_artifact(second, 1)["candidates"][0]

            self.assertEqual(left["candidate_id"], right["candidate_id"])
            self.assertNotEqual(left["support_ids"], right["support_ids"])
            self.assertNotEqual(left["candidate_digest"], right["candidate_digest"])

    def test_related_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            artifact = build_artifact(root, 4)
            candidate_id = artifact["candidates"][0]["candidate_id"]
            artifact["related_work"][candidate_id]["status"] = "reviewed"

            with self.assertRaises(ValueError):
                check_artifact(artifact, root)

    def test_retrieval_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            with patch("discover.scan_archive", side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    build_artifact(root, 4)

    def test_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_shard(root, shard())
            write_manifest(root)
            encoded = json.dumps(build_artifact(root, 4), ensure_ascii=False)

            self.assertNotIn(str(ROOT), encoded)


if __name__ == "__main__":
    unittest.main()
