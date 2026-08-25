from __future__ import annotations

import sys
import tempfile
import unittest
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from embed import (  # noqa: E402
    MODEL,
    MODEL_CONTEXT,
    MODEL_DIGEST,
    OLLAMA_VERSION,
    alias_exclusions,
    embed_batch,
    input_hash,
    load_parts,
    node_records,
    paper_text,
    save_parts,
    valid_vectors,
    vector_hash,
    vector_sha,
    verify_model,
)


def sample_atlas() -> dict:
    return {
        "topics": [{"id": "worlds", "label": "world models"}],
        "tricks": [{"id": "search", "label": "evolutionary search"}],
        "papers": [
            {
                "id": "paper-1",
                "title": "Learning compact world models",
                "reading": {"problem": "Model dynamics", "approach": "Predict states"},
                "topics": [{"id": "worlds"}],
                "tricks": [{"id": "search"}],
            },
            {
                "id": "paper-2",
                "title": "Searching for simulators",
                "reading": {"problem": "Find tasks", "approach": "Evolve programs"},
                "topics": [{"id": "worlds"}],
                "tricks": [],
            },
        ],
        "ideas": [
            {
                "id": "idea-1",
                "brief": {
                    "title": "Evolve environments",
                    "thesis": "Search for learning signal",
                },
            }
        ],
    }


class EmbedTests(unittest.TestCase):
    @staticmethod
    def response(payload: dict) -> BytesIO:
        return BytesIO(json.dumps(payload).encode())

    def test_embed_contract(self) -> None:
        expected = [[1.0, 2.0], [3.0, 4.0]]
        response = self.response({"embeddings": expected})

        with patch("embed.urllib.request.urlopen", return_value=response) as urlopen:
            embeddings = embed_batch(["alpha", "beta"])

        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(embeddings, expected)
        self.assertEqual(body["input"], ["alpha", "beta"])
        self.assertIs(body["truncate"], False)
        self.assertEqual(body["options"], {"num_ctx": MODEL_CONTEXT})

    def test_embed_invalid(self) -> None:
        for embedding in ([float("nan"), 1.0], [0.0, 0.0]):
            with self.subTest(embedding=embedding):
                response = self.response({"embeddings": [embedding]})
                with patch("embed.urllib.request.urlopen", return_value=response):
                    with self.assertRaisesRegex(RuntimeError, "invalid"):
                        embed_batch(["alpha"])

    def verify_responses(
        self,
        *,
        digest: str = MODEL_DIGEST,
        version: str = OLLAMA_VERSION,
        context: int = MODEL_CONTEXT,
    ) -> list[BytesIO]:
        return [
            self.response({"models": [{"name": MODEL, "digest": digest}]}),
            self.response({"version": version}),
            self.response({"model_info": {"bert.context_length": context}}),
        ]

    def test_digest_guard(self) -> None:
        with patch(
            "embed.urllib.request.urlopen",
            side_effect=self.verify_responses(digest="wrong"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pinned digest"):
                verify_model()

    def test_runtime_guard(self) -> None:
        with patch(
            "embed.urllib.request.urlopen",
            side_effect=self.verify_responses(version="wrong"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Ollama wrong"):
                verify_model()

    def test_context_guard(self) -> None:
        with patch(
            "embed.urllib.request.urlopen",
            side_effect=self.verify_responses(context=MODEL_CONTEXT - 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "context"):
                verify_model()

    def test_node_records(self) -> None:
        records = node_records(sample_atlas())

        self.assertEqual(len(records), 5)
        self.assertEqual(
            records[0][1],
            "machine learning research area: world models",
        )
        digest = vector_sha(np.ones((len(records), 3), dtype=np.float32))
        self.assertEqual(input_hash(records, digest), input_hash(records, digest))

    def test_reviewed_text(self) -> None:
        paper = sample_atlas()["papers"][0]
        detail = {
            "question": "Can dynamics be compressed?",
            "method": {"core_idea": "Learn predictive latent states."},
            "techniques": [{"id": "latent-rollout"}],
        }

        text = paper_text(paper, detail)

        self.assertIn("predictive latent states", text)
        self.assertIn("latent-rollout", text)

    def test_placeholder_omitted(self) -> None:
        paper = sample_atlas()["papers"][0]
        paper["reading"] = {
            "problem": "A full reading has not yet been completed.",
            "approach": "The collection currently provides only title-level evidence.",
        }

        text = paper_text(paper)

        self.assertNotIn("collection currently", text.casefold())

    def test_context_label(self) -> None:
        paper = sample_atlas()["papers"][0]
        paper["record_kind"] = "non_paper_context"

        text = paper_text(paper)

        self.assertTrue(text.startswith("collection entry:"))

    def test_field_budget(self) -> None:
        paper = sample_atlas()["papers"][0]
        detail = {
            "question": "question " * 100,
            "method": {
                "core_idea": "core " * 100,
                "mechanism": "mechanism " * 100,
            },
            "techniques": [{"id": "latent-rollout"}],
        }

        text = paper_text(paper, detail)

        for marker in (
            "research paper:",
            "question:",
            "core idea:",
            "mechanism:",
            "techniques:",
            "areas:",
        ):
            self.assertIn(marker, text)
        self.assertLessEqual(len(text), 800)

    def test_alias_exclusions(self) -> None:
        atlas = sample_atlas()
        atlas["papers"][0]["stable_id"] = "arxiv:1"
        atlas["papers"][1]["stable_id"] = "arxiv:1"
        records = node_records(atlas)

        excluded = alias_exclusions(atlas, records)

        self.assertIn("paper-2", excluded["paper-1"])
        self.assertIn("paper-1", excluded["paper-2"])

    def test_vector_cache(self) -> None:
        vectors = np.ones((2, 384), dtype=np.float32)

        self.assertTrue(valid_vectors(vectors, vector_sha(vectors)))
        wide = vectors.astype(np.float64)
        self.assertFalse(valid_vectors(wide, vector_sha(wide)))
        self.assertFalse(valid_vectors(vectors, "0" * 64))
        vectors[0] = 0
        self.assertFalse(valid_vectors(vectors, vector_sha(vectors)))
        vectors[0] = 1
        vectors[0, 0] = np.nan
        self.assertFalse(valid_vectors(vectors, vector_sha(vectors)))

    def test_input_hash(self) -> None:
        records = node_records(sample_atlas())
        other = [(node_id, f"{text} changed") for node_id, text in records]

        self.assertNotEqual(vector_hash(records), vector_hash(other))
        self.assertNotEqual(
            input_hash(records, "a" * 64), input_hash(records, "b" * 64)
        )

    def test_checkpoint(self) -> None:
        records = [("node-1", "one"), ("node-2", "two")]
        vectors = np.zeros((2, 384), dtype=np.float32)
        vectors[0] = 1
        done = np.asarray([True, False])
        with tempfile.TemporaryDirectory() as directory:
            part_path = Path(directory) / "parts.npz"
            with patch("embed.PART_PATH", part_path):
                save_parts(records, "digest", vectors, done)
                restored, restored_done = load_parts(records, "digest")

        self.assertTrue(np.array_equal(restored, vectors))
        self.assertTrue(np.array_equal(restored_done, done))

    def test_checkpoint_edits(self) -> None:
        records = [("node-1", "one"), ("node-2", "two")]
        vectors = np.vstack(
            [np.ones(384, dtype=np.float32), np.full(384, 2, dtype=np.float32)]
        )
        done = np.asarray([True, True])
        with tempfile.TemporaryDirectory() as directory:
            part_path = Path(directory) / "parts.npz"
            with patch("embed.PART_PATH", part_path):
                save_parts(records, "digest", vectors, done)
                reordered, reordered_done = load_parts(records[::-1], "other")
                edited, edited_done = load_parts(
                    [("node-1", "changed"), records[1]], "other"
                )
                with patch("embed.MODEL_DIGEST", "0" * 64):
                    changed, changed_done = load_parts(records, "other")

        self.assertTrue(np.array_equal(reordered, vectors[::-1]))
        self.assertTrue(reordered_done.all())
        self.assertEqual(edited_done.tolist(), [False, True])
        self.assertEqual(float(edited[0].sum()), 0)
        self.assertFalse(changed_done.any())
        self.assertEqual(float(changed.sum()), 0)

    def test_bad_checkpoint(self) -> None:
        records = [("node-1", "one"), ("node-2", "two")]
        vectors = np.ones((2, 384), dtype=np.float32)
        done = np.asarray([True, True])
        with tempfile.TemporaryDirectory() as directory:
            part_path = Path(directory) / "parts.npz"
            with patch("embed.PART_PATH", part_path):
                save_parts(records, "digest", vectors, done)
                with np.load(part_path) as saved:
                    values = {key: saved[key] for key in saved.files}
                values["vectors"][0, 0] = np.nan
                np.savez_compressed(part_path, **values)
                _, restored_done = load_parts(records, "digest")

        self.assertFalse(restored_done.any())


if __name__ == "__main__":
    unittest.main()
