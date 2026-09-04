from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import write_manifest, write_shard  # noqa: E402
from methods import build_artifact, check_artifact, iter_candidates  # noqa: E402
from methodtext import candidate_id, extract_methods  # noqa: E402


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(
    identifier: str,
    abstract: str,
    *,
    year: int,
    scope: str = "likely",
    trick: str = "routing-and-moe",
) -> dict:
    published = f"{year}-01-02T00:00:00Z"
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": "A method extraction fixture",
        "abstract": abstract,
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": published,
        "updated": published,
        "scope": scope,
        "relevance": {},
        "interest": {},
        "topics": [route("agents")],
        "tricks": [route(trick)],
    }


def shard(year: int, papers: list[dict]) -> dict:
    counts = {scope: 0 for scope in ("likely", "possible", "outside")}
    for item in papers:
        counts[item["scope"]] += 1
    return {
        "schema_version": 1,
        "policy_version": "methods-test-1",
        "month": f"{year}-01",
        "days": [],
        "counts": {"all": len(papers), **counts},
        "papers": papers,
    }


def corpus(root: Path) -> None:
    write_shard(
        root,
        shard(
            2023,
            [
                paper(
                    "2301.00001",
                    "We propose a novel Sparse-Routing Algorithm for agents. "
                    "Training uses contrastive learning.",
                    year=2023,
                ),
                paper(
                    "2301.00002",
                    "Our sparse routing algorithms improve control.",
                    year=2023,
                    scope="outside",
                ),
            ],
        ),
    )
    write_shard(
        root,
        shard(
            2024,
            [
                paper(
                    "2401.00001",
                    "This work presents the sparse routing algorithm. "
                    "It also studies contrastive learning.",
                    year=2024,
                    scope="possible",
                    trick="contrastive-learning",
                )
            ],
        ),
    )
    write_manifest(root)


def replace_asset(output: Path, index: dict, rows: list[dict]) -> None:
    """Replace one test asset while keeping its declared digest current."""
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path = output / "candidates.jsonl.gz"
    path.write_bytes(gzip.compress(payload.encode(), mtime=0))
    index["assets"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "index.json").write_text(json.dumps(index), encoding="utf-8")


class MethodsTests(unittest.TestCase):
    def test_open_vocab(self) -> None:
        rows = extract_methods(
            "We propose a novel Sparse-Routing Algorithms. "
            "Models are trained via contrastive learning."
        )

        self.assertEqual(
            {(row["label"], row["kind"]) for row in rows},
            {
                ("sparse routing algorithm", "method-noun"),
                ("contrastive learning", "process-technique"),
            },
        )
        self.assertEqual(
            extract_methods("We compare a method with the baseline."),
            [],
        )
        self.assertEqual(
            extract_methods(
                "We use training and an existing method with a promising approach."
            ),
            [],
        )
        self.assertEqual(
            candidate_id("sparse routing algorithm"),
            candidate_id("sparse routing algorithm"),
        )

    def test_phrase_forms(self) -> None:
        aliases = (
            "parameter efficient finetuning",
            "parameter efficient fine-tuning",
            "parameter efficient fine tuning",
        )
        for phrase in aliases:
            with self.subTest(phrase=phrase):
                rows = extract_methods(f"We use {phrase}.")
                self.assertEqual(
                    [row["label"] for row in rows],
                    ["parameter efficient fine tuning"],
                )

        rows = extract_methods(
            "We use contrastive learning and metric learning, plus graph embeddings "
            "and structured searches."
        )
        self.assertEqual(
            [row["label"] for row in rows],
            [
                "contrastive learning",
                "metric learning",
                "graph embedding",
                "structured search",
            ],
        )

    def test_quality_filter(self) -> None:
        noise = (
            "during training",
            "few training",
            "most existing method",
            "resulting framework",
            "mass loss",
            "physical mechanism",
        )
        for phrase in noise:
            with self.subTest(noise=phrase):
                self.assertEqual(extract_methods(phrase), [])

        legitimate = {
            "few-shot training": "few shot training",
            "mass conservation loss": "mass conservation loss",
            "physical simulation mechanism": "physical simulation mechanism",
            "resulting graph framework": "resulting graph framework",
        }
        for phrase, label in legitimate.items():
            with self.subTest(legitimate=phrase):
                self.assertEqual(
                    [row["label"] for row in extract_methods(phrase)], [label]
                )

        for wrapper in ("method", "approach", "framework"):
            source = f"We use a deep learning {wrapper}."
            with self.subTest(wrapper=wrapper):
                rows = extract_methods(source)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["label"], "deep learning")
                self.assertEqual(rows[0]["head"], "learning")
                self.assertEqual(rows[0]["kind"], "process-technique")
                start, end = rows[0]["span"]
                self.assertEqual(source[start:end], f"deep learning {wrapper}")

    def build(self, root: Path, output: Path) -> dict:
        corpus(root)
        return build_artifact(root, output, min_support=2)

    def test_builds_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            output = Path(directory) / "artifact"
            root.mkdir()
            value = self.build(root, output)
            rows = list(iter_candidates(output / "candidates.jsonl.gz"))

            self.assertEqual(check_artifact(root, output), value)
            self.assertIsNone(value["extraction"]["candidate_limit"])
            self.assertEqual(value["coverage"]["scanned_abstracts"], 3)
            self.assertEqual(len(value["curated_families"]), 24)
            self.assertEqual(
                [row["id"] for row in value["curated_families"]],
                sorted(row["id"] for row in value["curated_families"]),
            )
            routing = next(
                row for row in rows if row["label"] == "sparse routing algorithm"
            )
            self.assertEqual(routing["support_count"], 3)
            self.assertEqual(
                routing["scope_counts"], {"likely": 1, "possible": 1, "outside": 1}
            )
            self.assertEqual(routing["first_year"], "2023")
            self.assertEqual(routing["last_year"], "2024")
            self.assertEqual(len(routing["evidence"]), 3)

    def test_byte_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            root.mkdir()
            corpus(root)

            self.assertEqual(
                build_artifact(root, first, 2),
                build_artifact(root, second, 2),
            )
            self.assertEqual(
                (first / "candidates.jsonl.gz").read_bytes(),
                (second / "candidates.jsonl.gz").read_bytes(),
            )

    def test_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            output = Path(directory) / "artifact"
            root.mkdir()
            self.build(root, output)

            index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            changed = copy.deepcopy(index)
            changed["curated_families"][0]["paper_count"] += 1
            (output / "index.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deterministic corpus extraction"):
                check_artifact(root, output)

            (output / "index.json").write_text(json.dumps(index), encoding="utf-8")
            rows = list(iter_candidates(output / "candidates.jsonl.gz"))
            rows[0]["evidence"][0]["text"] = "tampered method"
            changed = copy.deepcopy(index)
            replace_asset(output, changed, rows)
            with self.assertRaisesRegex(ValueError, "does not reproduce"):
                check_artifact(root, output)

    def test_full_recompute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            output = Path(directory) / "artifact"
            root.mkdir()
            corpus(root)
            index = build_artifact(root, output, 2)
            rows = list(iter_candidates(output / "candidates.jsonl.gz"))
            row = rows[0]
            row["support_count"] += 100
            row["mention_count"] += 100
            row["scope_counts"]["likely"] += 100
            row["first_year"] = "1900"
            replace_asset(output, index, rows)
            with self.assertRaisesRegex(ValueError, "deterministic corpus extraction"):
                check_artifact(root, output)

            index = build_artifact(root, output, 2)
            index["coverage"]["quarantined_abstracts"] += 100
            index["coverage"]["extracted_mentions"] = 0
            index["coverage"]["distinct_extracted_candidates"] = 0
            (output / "index.json").write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deterministic corpus extraction"):
                check_artifact(root, output)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            output = Path(directory) / "artifact"
            root.mkdir()
            abstract = "We propose a sparse method architecture."
            write_shard(root, shard(2024, [paper("2401.00001", abstract, year=2024)]))
            write_manifest(root)
            index = build_artifact(root, output, 1)
            rows = list(iter_candidates(output / "candidates.jsonl.gz"))
            self.assertEqual(
                [row["label"] for row in rows], ["sparse method architecture"]
            )
            row = rows[0]
            start = abstract.index("sparse method")
            text = "sparse method"
            row.update(
                {
                    "id": candidate_id(text),
                    "label": text,
                    "head": "method",
                    "kind": "method-noun",
                }
            )
            row["evidence"][0]["span"] = [start, start + len(text)]
            row["evidence"][0]["text"] = text
            replace_asset(output, index, rows)
            with self.assertRaisesRegex(ValueError, "deterministic corpus extraction"):
                check_artifact(root, output)

    def test_schema_workflow(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/methods.schema.json").read_text(encoding="utf-8")
        )
        self.assertIn("candidate", schema["$defs"])
        workflow = (ROOT / ".github/workflows/methods.yml").read_text(encoding="utf-8")
        for text in (
            "types: [corpus-promoted]",
            "contents: write",
            "actions: write",
            "pipeline/methods.py",
            "pipeline/methodpack.py",
            "pipeline/methodbundle.py",
            "tests.test_methodpack",
            "tests.test_methodbundle",
            "actions/upload-artifact@v4",
            "retention-days: 30",
            "retention-days: 1",
            "always() && steps.corpus.outcome == 'success'",
            'tag="methods-v1"',
            'gh release upload "$METHOD_TAG"',
            '"$receipt" --clobber',
            "gh workflow run check.yml --ref main",
            "timeout-minutes: 360",
            "timeout-minutes: 180",
            "timeout-minutes: 150",
        ):
            with self.subTest(text=text):
                self.assertIn(text, workflow)
        for text in (
            "git push",
            "git commit",
            "continue-on-error: true",
        ):
            with self.subTest(text=text):
                self.assertNotIn(text, workflow)

    def test_minimum_support(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            output = Path(directory) / "artifact"
            root.mkdir()
            corpus(root)
            with self.assertRaisesRegex(ValueError, "positive integer"):
                build_artifact(root, output, 0)


if __name__ == "__main__":
    unittest.main()
