from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from assets import (  # noqa: E402
    PaperAssetError,
    ReadingAssetError,
    paper_asset,
    prune_papers,
    publish_reading_assets,
    reading_asset_filename,
    reading_public_path,
    stage_papers,
    validate_papers,
    validate_reading_assets,
)


class PaperAssetTests(unittest.TestCase):
    def test_paper_digest(self) -> None:
        bundle = {"schema_version": 1, "papers": [{"id": "paper-1"}]}
        metadata, content = paper_asset(bundle)

        self.assertEqual(metadata["bytes"], len(content))
        self.assertRegex(metadata["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(metadata["path"], f"/data/papers/{metadata['sha256']}.json")
        self.assertEqual(metadata["paper_count"], 1)
        self.assertEqual(paper_asset(dict(bundle))[0], metadata)

    def test_paper_retention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            output = public / "data/papers"
            public.mkdir()
            first = {"schema_version": 1, "papers": [{"id": "paper-1"}]}
            second = {"schema_version": 1, "papers": [{"id": "paper-2"}]}
            third = {"schema_version": 1, "papers": [{"id": "paper-3"}]}

            first_meta = stage_papers(output, first, public)
            second_meta = stage_papers(output, second, public)
            prune_papers(output, second_meta, first_meta["path"], public)
            validate_papers(output, second_meta, second, public)
            self.assertEqual(len(list(output.iterdir())), 2)
            prune_papers(output, second_meta, second_meta["path"], public)
            self.assertTrue((output / Path(first_meta["path"]).name).is_file())

            third_meta = stage_papers(output, third, public)
            prune_papers(output, third_meta, second_meta["path"], public)
            self.assertFalse((output / Path(first_meta["path"]).name).exists())
            self.assertTrue((output / Path(second_meta["path"]).name).is_file())
            self.assertTrue((output / Path(third_meta["path"]).name).is_file())

    def test_private_prior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            output = public / "data/papers"
            public.mkdir()
            private_url = "https://" + "x.com/account/status/1"
            first = {"schema_version": 1, "papers": [{"url": private_url}]}
            second = {
                "schema_version": 1,
                "papers": [{"url": "https://example.test"}],
            }
            first_meta = stage_papers(output, first, public)
            second_meta = stage_papers(output, second, public)

            prune_papers(output, second_meta, first_meta["path"], public)

            self.assertEqual(
                {path.name for path in output.iterdir()},
                {Path(second_meta["path"]).name},
            )

    def test_paper_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            external = root / "external"
            public.mkdir()
            external.mkdir()
            precious = external / "precious.json"
            precious.write_text('{"private":true}\n', encoding="utf-8")
            original = precious.read_bytes()
            output = public / "papers"
            output.symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(PaperAssetError, "symlink|outside"):
                stage_papers(output, {"papers": []}, public)
            self.assertEqual(precious.read_bytes(), original)

            output.unlink()
            data = public / "data"
            data.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(PaperAssetError, "symlink|outside"):
                stage_papers(data / "papers", {"papers": []}, public)
            self.assertEqual(precious.read_bytes(), original)

    def test_paper_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            output = public / "data/papers"
            public.mkdir()
            bundle = {"schema_version": 1, "papers": []}
            metadata = stage_papers(output, bundle, public)
            unexpected = output / "unexpected"
            unexpected.mkdir()

            with self.assertRaisesRegex(PaperAssetError, "non-regular"):
                prune_papers(output, metadata, trust_root=public)
            self.assertTrue((output / Path(metadata["path"]).name).is_file())


class ReadingAssetTests(unittest.TestCase):
    def test_path_safety(self) -> None:
        reading = {"stable_id": "arxiv:2506.12543", "question": "Test?"}
        first = reading_asset_filename("arxiv:2506.12543", reading)
        second = reading_asset_filename("arxiv/2506.12543", reading)

        self.assertRegex(
            first,
            r"^arxiv-2506-12543--[0-9a-f]{12}-[0-9a-f]{12}\.json$",
        )
        self.assertNotEqual(first, second)
        self.assertEqual(
            reading_public_path("arxiv:2506.12543", reading),
            f"/data/readings/{first}",
        )
        self.assertFalse(
            re.search(
                r"(^|/)\.\.($|/)",
                reading_public_path("../paper", reading),
            )
        )

    def test_revision_address(self) -> None:
        stable_id = "arxiv:2506.12543"
        first = {"stable_id": stable_id, "question": "Original question?"}
        revised = {**first, "question": "Revised question?"}

        self.assertNotEqual(
            reading_asset_filename(stable_id, first),
            reading_asset_filename(stable_id, revised),
        )
        self.assertNotEqual(
            reading_public_path(stable_id, first),
            reading_public_path(stable_id, revised),
        )

    def test_publish_pruning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "public"
            source_dir.mkdir()
            output_dir.mkdir()
            source = source_dir / "paper.json"
            source.write_text(
                '{\n  "stable_id": "arxiv:1", "reading_depth": "full_text"\n}\n',
                encoding="utf-8",
            )
            (output_dir / "stale.json").write_text("{}", encoding="utf-8")

            paths = publish_reading_assets(source_dir, output_dir)

            reading = json.loads(source.read_text(encoding="utf-8"))
            published = output_dir / reading_asset_filename("arxiv:1", reading)
            self.assertEqual(
                paths,
                {"arxiv:1": reading_public_path("arxiv:1", reading)},
            )
            self.assertEqual(published.read_bytes(), source.read_bytes())
            self.assertFalse((output_dir / "stale.json").exists())

    def test_invalid_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "public"
            source_dir.mkdir()
            reading = {"stable_id": "arxiv:1", "reading_depth": "full_text"}
            (source_dir / "paper.json").write_text(
                json.dumps(reading) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ReadingAssetError, "missing"):
                validate_reading_assets(source_dir, output_dir, {"arxiv:1": reading})

            publish_reading_assets(source_dir, output_dir)
            published = output_dir / reading_asset_filename("arxiv:1", reading)
            published.write_text(
                json.dumps({**reading, "question": "changed"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ReadingAssetError, "bytes are stale"):
                validate_reading_assets(source_dir, output_dir, {"arxiv:1": reading})

            publish_reading_assets(source_dir, output_dir)
            (output_dir / "orphan.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ReadingAssetError, "stale"):
                validate_reading_assets(source_dir, output_dir, {"arxiv:1": reading})

    def test_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "public"
            source_dir.mkdir()
            reading = {"stable_id": "arxiv:1", "reading_depth": "full_text"}
            (source_dir / "paper.json").write_text(
                json.dumps(reading), encoding="utf-8"
            )
            publish_reading_assets(source_dir, output_dir)

            with self.assertRaisesRegex(ReadingAssetError, "source reading files"):
                validate_reading_assets(
                    source_dir,
                    output_dir,
                    {"arxiv:2": {**reading, "stable_id": "arxiv:2"}},
                )

    def test_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "public"
            source_dir.mkdir()
            reading = {"stable_id": "arxiv:1", "reading_depth": "full_text"}
            for name in ("first.json", "second.json"):
                (source_dir / name).write_text(json.dumps(reading), encoding="utf-8")

            with self.assertRaisesRegex(
                ReadingAssetError, "Duplicate reading stable ID"
            ):
                publish_reading_assets(source_dir, output_dir)

    def test_filename_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "reviewed"
            output_dir = root / "public"
            source_dir.mkdir()
            for index in (1, 2):
                (source_dir / f"paper-{index}.json").write_text(
                    json.dumps(
                        {"stable_id": f"arxiv:{index}", "reading_depth": "full_text"}
                    ),
                    encoding="utf-8",
                )

            with patch(
                "assets.reading_asset_filename",
                return_value="forced-collision.json",
            ):
                with self.assertRaisesRegex(ReadingAssetError, "filenames collide"):
                    publish_reading_assets(source_dir, output_dir)

            self.assertFalse(output_dir.exists())

    def test_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "reviewed"
            output_dir = root / "public-readings"
            source_dir.mkdir()
            source = source_dir / "paper.json"
            source.write_text(
                '{"stable_id":"arxiv:1","reading_depth":"full_text"}\n',
                encoding="utf-8",
            )
            original_bytes = source.read_bytes()
            output_dir.symlink_to(source_dir, target_is_directory=True)

            with self.assertRaisesRegex(ReadingAssetError, "symlink|overlap"):
                publish_reading_assets(source_dir, output_dir)

            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(list(source_dir.iterdir()), [source])

    def test_symlink_pruning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "reviewed"
            unrelated_dir = root / "other-curated-judgments"
            output_dir = root / "public-readings"
            source_dir.mkdir()
            unrelated_dir.mkdir()
            (source_dir / "paper.json").write_text(
                '{"stable_id":"arxiv:1","reading_depth":"full_text"}\n',
                encoding="utf-8",
            )
            precious = unrelated_dir / "precious-review.json"
            precious.write_text('{"human":"judgment"}\n', encoding="utf-8")
            original_bytes = precious.read_bytes()
            output_dir.symlink_to(unrelated_dir, target_is_directory=True)

            with self.assertRaisesRegex(ReadingAssetError, "symlink"):
                publish_reading_assets(source_dir, output_dir)

            self.assertEqual(precious.read_bytes(), original_bytes)
            self.assertEqual(list(unrelated_dir.iterdir()), [precious])

    def test_symlink_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "reviewed"
            external_root = root / "external-root"
            source_dir.mkdir()
            external_root.mkdir()
            (source_dir / "paper.json").write_text(
                '{"stable_id":"arxiv:1","reading_depth":"full_text"}\n',
                encoding="utf-8",
            )
            external_readings = external_root / "readings"
            external_readings.mkdir()
            precious = external_readings / "precious-review.json"
            precious.write_text('{"human":"judgment"}\n', encoding="utf-8")
            original_bytes = precious.read_bytes()
            public_parent = root / "public-parent"
            public_parent.symlink_to(external_root, target_is_directory=True)

            with self.assertRaisesRegex(ReadingAssetError, "traverse a symlink"):
                publish_reading_assets(source_dir, public_parent / "readings")

            self.assertEqual(precious.read_bytes(), original_bytes)
            self.assertEqual(list(external_readings.iterdir()), [precious])

    def test_symlink_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "reviewed"
            source_dir.mkdir()
            external = root / "external.json"
            external.write_text('{"stable_id":"arxiv:1"}', encoding="utf-8")
            (source_dir / "paper.json").symlink_to(external)

            with self.assertRaisesRegex(ReadingAssetError, "non-symlink"):
                publish_reading_assets(source_dir, root / "public")


if __name__ == "__main__":
    unittest.main()
