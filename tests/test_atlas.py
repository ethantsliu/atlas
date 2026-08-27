import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import atlas as build_atlas  # noqa: E402
from atlas import (  # noqa: E402
    build_ideas,
    paper_bundle,
    public_core,
    reconstruct_atlas,
    taxon_label,
)
from assets import paper_asset, reading_public_path  # noqa: E402


def make_payload(detail_path: str, generated_at: str) -> dict:
    return {
        "meta": {"generated_at": generated_at},
        "papers": [
            {
                "id": "paper-1",
                "stable_id": "arxiv:1",
                "title": "A Paper",
                "full_reading_path": detail_path,
            }
        ],
        "layout": {
            "model": "fixture",
            "method": "fixture-3d",
            "input_sha256": "a" * 64,
            "node_count": 1,
            "neighbor_count": 0,
            "clusters": [{"id": "cluster-one"}],
            "positions": {"paper-1": [0, 0, 0]},
            "neighbors": {"paper-1": []},
            "node_clusters": {"paper-1": "cluster-one"},
        },
    }


def read_bundle(web_path: Path) -> tuple[dict, dict]:
    core = json.loads(web_path.read_text(encoding="utf-8"))
    asset_path = web_path.parents[1] / core["paper_asset"]["path"].lstrip("/")
    return core, json.loads(asset_path.read_text(encoding="utf-8"))


def flagship() -> dict:
    return {
        "id": "reviewed-test-idea",
        "topic_ids": [],
        "trick_ids": [],
        "feasibility": {"score": 7.0},
        "brief": {},
    }


class BuildIdeasTests(unittest.TestCase):
    def test_repo_free(self) -> None:
        ideas = build_ideas([], [flagship()])

        self.assertEqual(ideas[0]["repo_ids"], [])
        self.assertEqual(ideas[0]["brief"]["repo_ids"], [])
        self.assertNotIn("personal_relevance", ideas[0])
        self.assertNotIn("personal_paper_ids", ideas[0])

    def test_training_labels(self) -> None:
        self.assertEqual(taxon_label("pre-training"), "pretraining")
        self.assertEqual(taxon_label("post-training"), "post-training")

    def test_public_split(self) -> None:
        payload = {
            "meta": {"generated_at": "2026-08-25T00:00:00Z"},
            "topics": [{"id": "a"}],
            "tricks": [],
            "ideas": [],
            "papers": [{"id": "paper-1", "title": "A Paper"}],
            "layout": {
                "model": "all-minilm",
                "positions": {"topic:a": [0, 0, 0], "paper-1": [1, 1, 1]},
                "neighbors": {"topic:a": [], "paper-1": []},
                "node_clusters": {"topic:a": "c1", "paper-1": "c1"},
            },
        }
        bundle = paper_bundle(payload)
        metadata, _ = paper_asset(bundle)
        core = public_core(payload, metadata)

        self.assertEqual(set(core["layout"]["positions"]), {"topic:a"})
        self.assertEqual(set(bundle["layout"]["positions"]), {"paper-1"})
        self.assertEqual(reconstruct_atlas(core, bundle), payload)

        missing = deepcopy(bundle)
        missing["layout"]["positions"].pop("paper-1")
        with self.assertRaisesRegex(ValueError, "coverage"):
            reconstruct_atlas(core, missing)

        changed_time = {**payload, "meta": {"generated_at": "2027-01-01T00:00:00Z"}}
        self.assertEqual(paper_bundle(changed_time), bundle)


class PublicationOrderingTests(unittest.TestCase):
    def test_base_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "generated/atlas.json"
            inventory_path = root / "generated/inventory.json"
            progress_path = root / "generated/progress.json"
            web_path = root / "public/atlas.json"
            web_path.parent.mkdir(parents=True)
            web_path.write_text('{"published":true}', encoding="utf-8")
            payload = {"meta": {"paper_count": 1}, "papers": []}

            with patch.multiple(
                build_atlas,
                OUTPUT_PATH=output,
                SOURCE_INVENTORY_PATH=inventory_path,
                PROGRESS_PATH=progress_path,
            ):
                build_atlas.write_base(payload, {"records": []}, {"full_readings": 0})

            self.assertEqual(json.loads(output.read_text()), payload)
            self.assertTrue(inventory_path.is_file())
            self.assertTrue(progress_path.is_file())
            self.assertEqual(json.loads(web_path.read_text()), {"published": True})

            with self.assertRaisesRegex(ValueError, "must not contain"):
                build_atlas.write_base({**payload, "layout": {}}, {}, {})

    def test_publish_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readings_dir = root / "reviewed"
            web_root = root / "web/public"
            web_readings_dir = web_root / "data/readings"
            web_papers_dir = web_root / "data/papers"
            output_path = root / "generated/atlas.json"
            web_path = web_root / "data/atlas.json"
            readings_dir.mkdir()
            reading_path = readings_dir / "paper.json"
            old_reading = {
                "stable_id": "arxiv:1",
                "reading_depth": "full_text",
                "question": "Old question?",
            }
            reading_path.write_text(json.dumps(old_reading), encoding="utf-8")
            old_detail_path = reading_public_path("arxiv:1", old_reading)
            old_atlas = make_payload(old_detail_path, "2026-08-24T00:00:00Z")

            new_reading = {**old_reading, "question": "New question?"}
            reading_path.write_text(json.dumps(new_reading), encoding="utf-8")
            new_detail_path = reading_public_path("arxiv:1", new_reading)
            new_atlas = make_payload(new_detail_path, "2026-08-25T00:00:00Z")

            publication_paths = {
                "READINGS_DIR": readings_dir,
                "WEB_READINGS_DIR": web_readings_dir,
                "WEB_PAPERS_DIR": web_papers_dir,
                "WEB_ROOT": web_root,
                "OUTPUT_PATH": output_path,
                "WEB_PATH": web_path,
            }
            with patch.multiple(build_atlas, **publication_paths):
                reading_path.write_text(json.dumps(old_reading), encoding="utf-8")
                build_atlas.publish_atlas_payload(old_atlas)
                old_core, old_bundle = read_bundle(web_path)
                old_paper_path = web_root / old_core["paper_asset"]["path"].lstrip("/")
                self.assertEqual(old_bundle["papers"], old_atlas["papers"])

                reading_path.write_text(json.dumps(new_reading), encoding="utf-8")
                drifted_reading = {**new_reading, "question": "Drifted question?"}
                reading_path.write_text(json.dumps(drifted_reading), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "readings changed"):
                    build_atlas.publish_atlas_payload(new_atlas)
                self.assertEqual(json.loads(web_path.read_text()), old_core)
                self.assertTrue((web_root / old_detail_path.lstrip("/")).is_file())
                reading_path.write_text(json.dumps(new_reading), encoding="utf-8")

                real_write = build_atlas.atomic_write_text

                def fail_core(path: Path, content: str) -> None:
                    if path == web_path:
                        raise RuntimeError("simulated index publication failure")
                    real_write(path, content)

                with patch.object(
                    build_atlas,
                    "atomic_write_text",
                    side_effect=fail_core,
                ):
                    with self.assertRaisesRegex(RuntimeError, "simulated"):
                        build_atlas.publish_atlas_payload(new_atlas)

                visible_after_copy_failure, copy_bundle = read_bundle(web_path)
                old_visible_detail = web_root / copy_bundle["papers"][0][
                    "full_reading_path"
                ].lstrip("/")
                self.assertTrue(old_visible_detail.is_file())
                self.assertEqual(visible_after_copy_failure, old_core)
                self.assertTrue(old_paper_path.is_file())

                with patch.object(
                    build_atlas,
                    "prune_reading_assets",
                    side_effect=RuntimeError("simulated prune failure"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "simulated"):
                        build_atlas.publish_atlas_payload(new_atlas)

                _, visible_bundle = read_bundle(web_path)
                new_visible_detail = web_root / visible_bundle["papers"][0][
                    "full_reading_path"
                ].lstrip("/")
                self.assertTrue(new_visible_detail.is_file())

                build_atlas.publish_atlas_payload(new_atlas)

            final_core, final_bundle = read_bundle(web_path)
            self.assertEqual(reconstruct_atlas(final_core, final_bundle), new_atlas)
            self.assertEqual(json.loads(output_path.read_text()), new_atlas)
            self.assertTrue(new_visible_detail.is_file())
            self.assertFalse(old_visible_detail.exists())
            self.assertTrue(old_paper_path.is_file())


if __name__ == "__main__":
    unittest.main()
