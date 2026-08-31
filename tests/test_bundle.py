from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from bundle import pack_tree, unpack_tree  # noqa: E402


class BundleTests(unittest.TestCase):
    def test_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            source.mkdir()
            (source / "state.json").write_text('{"count": 3}\n', encoding="utf-8")
            archive = base / "legacy.tar.gz"
            with tarfile.open(archive, "w:gz", compresslevel=9) as bundle:
                bundle.add(source / "state.json", arcname="state.json")

            restored = base / "restored"
            unpack_tree(archive, restored, 10, 1024)

            self.assertEqual(
                (restored / "state.json").read_text(encoding="utf-8"),
                '{"count": 3}\n',
            )

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            (source / "stage").mkdir(parents=True)
            (source / "stage/page.json.gz").write_bytes(b"page bytes")
            archive = base / "checkpoint.tar.gz"

            pack_tree(source, archive)

            with tarfile.open(archive, "r:gz") as bundle:
                saved = bundle.extractfile("stage/page.json.gz")
                self.assertIsNotNone(saved)
                self.assertEqual(saved.read(), b"page bytes")

    def test_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive = base / "unsafe.tar.gz"
            content = b"escape"
            with tarfile.open(archive, "w:gz") as bundle:
                safe = tarfile.TarInfo("safe")
                safe.size = len(content)
                bundle.addfile(safe, io.BytesIO(content))
                unsafe = tarfile.TarInfo("../escape")
                unsafe.size = len(content)
                bundle.addfile(unsafe, io.BytesIO(content))

            restored = base / "restore"
            with self.assertRaisesRegex(ValueError, "unsafe"):
                unpack_tree(archive, restored, 10, 1024)

            self.assertFalse(restored.exists())
            self.assertFalse((base / "escape").exists())


if __name__ == "__main__":
    unittest.main()
