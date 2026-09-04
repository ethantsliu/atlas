from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from methodbundle import load_receipt, pack_bundle, unpack_bundle  # noqa: E402
from methodpack import build_pack  # noqa: E402
from methodtree import json_bytes  # noqa: E402
from tests.test_methodpack import RELEASE, source_pack, tiny_limits  # noqa: E402


def browser_pack(root: Path) -> Path:
    """Build one valid browser tree for release-bundle tests."""
    source = source_pack(root)
    browser = root / "browser"
    build_pack(source, browser, RELEASE)
    return browser


class MethodBundleTests(unittest.TestCase):
    def test_catalog_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            browser = root / "browser"
            build_pack(
                source_pack(root, 40),
                browser,
                RELEASE,
                limits=tiny_limits(),
                package_cap=100_000,
            )
            release = root / "release"
            value = pack_bundle(browser, release)

            self.assertEqual(value["tier"], "catalog-only")
            unpack_bundle(
                release / "browser.json",
                release / value["browser"]["path"],
                root / "restored",
            )

    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            browser = browser_pack(root)
            release = root / "release"

            value = pack_bundle(browser, release)
            restored = root / "restored"
            actual = unpack_bundle(
                release / "browser.json",
                release / value["browser"]["path"],
                restored,
            )

            self.assertEqual(actual, value)
            self.assertEqual(
                {path.name: path.read_bytes() for path in browser.iterdir()},
                {path.name: path.read_bytes() for path in restored.iterdir()},
            )
            self.assertEqual(load_receipt(release / "browser.json"), value)

    def test_tar_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            browser = browser_pack(root)
            first = pack_bundle(browser, root / "first")
            second = pack_bundle(browser, root / "second")

            self.assertEqual(first, second)
            self.assertEqual(
                (root / "first" / first["browser"]["path"]).read_bytes(),
                (root / "second" / second["browser"]["path"]).read_bytes(),
            )

    def test_archive_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "release"
            value = pack_bundle(browser_pack(root), release)
            archive = release / value["browser"]["path"]
            archive.write_bytes(archive.read_bytes() + b"tamper")

            with self.assertRaisesRegex(ValueError, "missing or drifted"):
                unpack_bundle(release / "browser.json", archive, root / "restored")

    def test_candidate_binding(self) -> None:
        changes = {
            "path": "candidates-" + "0" * 64 + ".jsonl.gz",
            "encoding": "json",
            "sha256": "0" * 64,
            "bytes": 1,
            "row_count": 999,
        }
        for field, changed in changes.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                release = root / "release"
                value = pack_bundle(browser_pack(root), release)
                receipt = release / "browser.json"
                altered = json.loads(receipt.read_text(encoding="utf-8"))
                altered["candidates"][field] = changed
                receipt.write_bytes(json_bytes(altered))

                with self.assertRaisesRegex(ValueError, "invalid|does not bind"):
                    unpack_bundle(
                        receipt,
                        release / value["browser"]["path"],
                        root / "restored",
                    )
                self.assertFalse((root / "restored").exists())

    def test_receipt_strictness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "release"
            pack_bundle(browser_pack(root), release)
            receipt = release / "browser.json"
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["browser"]["unpacked_bytes"] = 104857601
            receipt.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not canonical|invalid"):
                load_receipt(receipt)

    def test_workflow_boundary(self) -> None:
        methods = (ROOT / ".github/workflows/methods.yml").read_text(encoding="utf-8")
        deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        extract, publish = methods.split("\n  publish:\n", 1)
        self.assertIn("contents: read", extract)
        self.assertNotIn("contents: write", extract)
        self.assertIn("contents: write", publish)
        self.assertLess(
            publish.index("current_sha="), publish.index("gh release upload")
        )
        self.assertFalse((ROOT / "web/public/data/methods").exists())
        for text in (
            "pipeline/methodpack.py",
            "pipeline/methodbundle.py",
            "candidates-$candidate_sha.jsonl.gz",
            "browser-[0-9a-f]{64}",
            "compression-level: 0",
            "contents: write",
            "gh workflow run check.yml --ref main",
        ):
            with self.subTest(text=text):
                self.assertIn(text, methods)
        for text in (
            "pipeline/methodbundle.py",
            "--unpack",
            "test ! -e web/dist/data/methods",
            "996147200",
            'cmp "$release/browser.json"',
            "archive_size",
            '"sha256:$archive_sha"',
            '"sha256:$candidate_sha"',
        ):
            with self.subTest(text=text):
                self.assertIn(text, deploy)


if __name__ == "__main__":
    unittest.main()
