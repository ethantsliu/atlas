from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import write_manifest, write_shard  # noqa: E402
from catalog import build_catalog  # noqa: E402
from ontology import TRICKS  # noqa: E402
from questions import (  # noqa: E402
    EVIDENCE_RELATION,
    artifact_hash,
    build_artifact,
    check_artifact,
    question_id,
)


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(index: int, year: int, subjects: list[str], tricks: list[str]) -> dict:
    identifier = f"{year % 100:02d}01.{index:05d}"
    published = f"{year}-01-02T00:00:00Z"
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A controlled learning systems study",
        "abstract": "We compare controlled learning systems across tasks.",
        "authors": [f"Author {index % 4}"],
        "categories": subjects,
        "primary_category": subjects[0],
        "published": published,
        "updated": published,
        "scope": "likely",
        "relevance": {},
        "interest": {},
        "topics": [route("agents")],
        "tricks": [route(identifier) for identifier in tricks],
    }


def shard(year: int, papers: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "policy_version": "questions-test-1",
        "month": f"{year}-01",
        "days": [],
        "counts": {
            "all": len(papers),
            "likely": len(papers),
            "possible": 0,
            "outside": 0,
        },
        "papers": papers,
    }


class QuestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subjects = [f"cs.X{index:02d}" for index in range(72)]
        tricks = sorted(TRICKS)
        first = [
            paper(offset * 6 + index, 2023, subjects, [trick])
            for offset, trick in enumerate(tricks)
            for index in range(1, 7)
        ]
        second = [
            paper(offset * 6 + index, 2024, subjects, [trick])
            for offset, trick in enumerate(tricks)
            for index in range(1, 7)
        ]
        write_shard(self.root, shard(2023, first))
        write_shard(self.root, shard(2024, second))
        write_manifest(self.root)
        self.catalog = build_catalog(self.root, limit=1710)

    def test_workflow(self) -> None:
        workflow = (ROOT / ".github/workflows/catalog.yml").read_text(encoding="utf-8")
        for text in (
            "pipeline/questions.py",
            "tests.test_questions",
            "atlas-question-candidates-",
            "retention-days: 30",
            'test "$directions" -gt 310',
            'test "$questions" -eq "$directions"',
            'test "$source_sha" = "$catalog_sha"',
            'test "$bytes" -le 12582912',
        ):
            with self.subTest(text=text):
                self.assertIn(text, workflow)
        self.assertNotIn('git add "$QUESTIONS_OUTPUT"', workflow)
        self.assertEqual(workflow.count('--archive "$ARCHIVE_ROOT"'), 2)

    def test_build_scale(self) -> None:
        value = build_artifact(self.catalog)

        self.assertIs(check_artifact(value, self.catalog, self.root), value)
        self.assertEqual(len(self.catalog["directions"]), 1710)
        self.assertGreater(len(value["candidates"]), 310)
        self.assertEqual(
            value["counts"],
            {
                "source_directions": 1710,
                "unreviewed_candidate_questions": 1710,
                "reviewed_ideas_added": 0,
            },
        )
        self.assertEqual(value["content_sha256"], artifact_hash(value))

    def test_candidate_semantics(self) -> None:
        candidate = build_artifact(self.catalog)["candidates"][0]

        self.assertEqual(candidate["review_status"], "unreviewed")
        self.assertEqual(candidate["novelty_status"], "not-assessed")
        self.assertEqual(candidate["feasibility_status"], "not-assessed")
        self.assertEqual(candidate["evidence_relation"], EVIDENCE_RELATION)
        self.assertEqual(candidate["rank"], 1)
        self.assertEqual(
            candidate["support_ids"],
            [row["id"] for row in candidate["support_refs"]],
        )
        identity = candidate["identity"]
        self.assertEqual(
            candidate["id"],
            question_id(identity["subject_id"], identity["technique_id"]),
        )
        self.assertIn("better, worse, or unchanged", candidate["question"])

    def test_stable_identity(self) -> None:
        first = build_artifact(self.catalog)["candidates"][0]
        changed = copy.deepcopy(self.catalog)
        changed["directions"][0]["support_count"] += 1

        self.assertEqual(
            first["id"],
            question_id(
                changed["directions"][0]["subject_id"],
                changed["directions"][0]["technique_id"],
            ),
        )

    def test_rejects_tampering(self) -> None:
        value = build_artifact(self.catalog)
        changed = copy.deepcopy(value)
        changed["candidates"][0]["review_status"] = "reviewed"
        changed["content_sha256"] = artifact_hash(changed)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            check_artifact(changed, self.catalog)

        changed = copy.deepcopy(value)
        changed["candidates"][0]["support_refs"][0]["row"] += 1
        changed["content_sha256"] = artifact_hash(changed)
        with self.assertRaisesRegex(ValueError, "source catalog"):
            check_artifact(changed, self.catalog)

        changed = copy.deepcopy(value)
        changed["notice"] += " changed"
        with self.assertRaisesRegex(ValueError, "content digest"):
            check_artifact(changed, self.catalog)

    def test_cli_roundtrip(self) -> None:
        catalog = self.root / "catalog.json"
        output = self.root / "questions.json"
        catalog.write_text(json.dumps(self.catalog), encoding="utf-8")
        command = [
            sys.executable,
            str(ROOT / "pipeline/questions.py"),
            "--catalog",
            str(catalog),
            "--output",
            str(output),
        ]

        built = subprocess.run(command, check=True, capture_output=True, text=True)
        checked = subprocess.run(
            [*command, "--check", "--archive", str(self.root)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("Built 1,710 unreviewed candidates", built.stdout)
        self.assertIn("Validated 1,710 unreviewed candidates", checked.stdout)


if __name__ == "__main__":
    unittest.main()
