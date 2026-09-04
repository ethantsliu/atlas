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
from methodcheck import check_pack, check_search, leaf_rows  # noqa: E402
from methodpack import (  # noqa: E402
    INDEX_GZIP,
    INDEX_RAW,
    build_pack,
    load_source,
)
from methodcatalog import IDENTITY_COLUMNS, full_row_sha256  # noqa: E402
from methods import build_artifact  # noqa: E402
from methodtree import (  # noqa: E402
    Limits,
    PackageTooLarge,
    compact_row,
    fits,
    gzip_length,
    json_bytes,
    row_key,
    search_words,
)
from tests.test_methods import corpus, paper, shard  # noqa: E402


RELEASE = (
    "https://github.com/ethantsliu/atlas/releases/download/"
    "methods-v1/candidates.jsonl.gz"
)


def source_pack(root: Path, count: int = 1) -> Path:
    """Build a valid method artifact with many deliberately hot search terms."""
    archive = root / "archive"
    source = root / "source"
    archive.mkdir()
    if count == 1:
        corpus(archive)
        build_artifact(archive, source, 2)
        return source
    papers = [
        paper(
            f"2401.{index + 1:05d}",
            f"We use alpha{index:03d} routing algorithm.",
            year=2024,
        )
        for index in range(count)
    ]
    write_shard(archive, shard(2024, papers))
    write_manifest(archive)
    build_artifact(archive, source, 1)
    return source


def file_map(root: Path) -> dict[str, bytes]:
    """Read a complete generated package for byte-determinism comparison."""
    return {path.name: path.read_bytes() for path in sorted(root.iterdir())}


def tiny_limits() -> Limits:
    """Force recursive search and detail routing while allowing one-row leaves."""
    return Limits(
        search_raw=700,
        search_gzip=500,
        detail_raw=1100,
        detail_gzip=900,
        router_raw=8192,
        router_gzip=4096,
    )


class MethodPackTests(unittest.TestCase):
    def test_public_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root)
            output = root / "public"

            value = build_pack(source, output, RELEASE)

            self.assertEqual(check_pack(output), value)
            self.assertEqual(value["generator_version"], "methods-browser-1")
            self.assertEqual(value["tier"], "full-evidence")
            self.assertEqual(
                set(value["assets"]),
                {"summary", "top", "search", "details", "download"},
            )
            self.assertEqual(value["assets"]["download"]["url"], RELEASE)
            self.assertNotIn("candidates.jsonl.gz", file_map(output))
            self.assertTrue(
                fits((output / "index.json").read_bytes(), INDEX_RAW, INDEX_GZIP)
            )
            for name in ("summary", "top", "search", "details"):
                descriptor = value["assets"][name]
                content = (output / descriptor["path"]).read_bytes()
                self.assertEqual(descriptor["bytes"], len(content))
                self.assertEqual(
                    descriptor["sha256"], hashlib.sha256(content).hexdigest()
                )
                self.assertNotIn("gzip_bytes", descriptor)

    def test_byte_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root, 12)
            first = root / "first"
            second = root / "second"

            build_pack(source, first, RELEASE)
            build_pack(source, second, RELEASE)

            self.assertEqual(file_map(first), file_map(second))

    def test_catalog_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root, 40)
            output = root / "public"
            limits = tiny_limits()
            source_index, source_rows, _ = load_source(source)

            value = build_pack(
                source, output, RELEASE, limits=limits, package_cap=100_000
            )

            self.assertEqual(value["tier"], "catalog-only")
            self.assertEqual(value["extraction"], source_index["extraction"])
            self.assertEqual(
                value["coverage"]["qualified_candidates"], len(source_rows)
            )
            self.assertIn(
                "Evidence spans are available only in the immutable full release download.",
                value["notice"],
            )
            self.assertLessEqual(
                sum(path.stat().st_size for path in output.iterdir()), 100_000
            )
            decoded = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in output.iterdir()
                if path.suffix == ".json"
            ]
            self.assertFalse(any('"evidence"' in json.dumps(body) for body in decoded))
            posting_leaves = [body for body in decoded if "ordinals" in body]
            self.assertTrue(posting_leaves)
            for body in posting_leaves:
                self.assertEqual(body["ordinals"], sorted(set(body["ordinals"])))
                self.assertFalse(any(key in body for key in ("id", "label", "rows")))
            identities = sorted(
                (
                    dict(zip(IDENTITY_COLUMNS, row, strict=True))
                    for body in decoded
                    for row in body.get("rows", [])
                    if body.get("route_kind") == "detail"
                    and body.get("columns") == list(IDENTITY_COLUMNS)
                ),
                key=lambda row: row["ordinal"],
            )
            self.assertEqual(
                [row["ordinal"] for row in identities], list(range(len(source_rows)))
            )
            self.assertEqual(
                [row["full_row_sha256"] for row in identities],
                [full_row_sha256(row) for row in source_rows],
            )
            self.assertEqual(check_pack(output, limits), value)

    def test_catalog_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root, 40)
            first = root / "first"
            second = root / "second"
            for output in (first, second):
                build_pack(
                    source,
                    output,
                    RELEASE,
                    limits=tiny_limits(),
                    package_cap=100_000,
                )
            self.assertEqual(file_map(first), file_map(second))

    def test_catalog_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            with self.assertRaises(PackageTooLarge):
                build_pack(
                    source_pack(root, 40),
                    output,
                    RELEASE,
                    limits=tiny_limits(),
                    package_cap=50_000,
                )
            self.assertFalse(output.exists())

    def test_adaptive_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root, 40)
            output = root / "public"
            limits = tiny_limits()

            value = build_pack(source, output, RELEASE, limits)

            self.assertEqual(check_pack(output, limits), value)
            names = set(file_map(output))
            self.assertTrue(any(name.startswith("search-route-") for name in names))
            self.assertTrue(any(name.startswith("detail-route-") for name in names))
            for path in output.glob("search-*.json"):
                if "rows" not in json.loads(path.read_text(encoding="utf-8")):
                    continue
                self.assertLessEqual(len(path.read_bytes()), limits.search_raw)
                self.assertLessEqual(gzip_length(path.read_bytes()), limits.search_gzip)
            for path in output.glob("detail-*.json"):
                if "rows" not in json.loads(path.read_text(encoding="utf-8")):
                    continue
                self.assertLessEqual(len(path.read_bytes()), limits.detail_raw)
                self.assertLessEqual(gzip_length(path.read_bytes()), limits.detail_gzip)

    def test_hash_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            build_pack(source_pack(root), output, RELEASE)
            index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            path = output / index["assets"]["top"]["path"]
            path.write_bytes(path.read_bytes() + b" ")

            with self.assertRaisesRegex(ValueError, "descriptor is stale"):
                check_pack(output)

    def test_count_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            build_pack(source_pack(root), output, RELEASE)
            index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            index["assets"]["top"]["row_count"] += 1
            (output / "index.json").write_bytes(json_bytes(index))

            with self.assertRaisesRegex(ValueError, "top descriptor row count"):
                check_pack(output)

    def test_order_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root, 3)
            _, rows, _ = load_source(source)
            details: dict[str, dict] = {}
            searches: list[tuple[str, str, dict]] = []
            descriptor = {
                "prefix": rows[0]["id"].split(":")[1][:2],
                "row_count": 2,
            }
            body = {"rows": [rows[0], rows[0]]}
            with self.assertRaisesRegex(ValueError, "duplicate"):
                leaf_rows(body, descriptor, "detail", 1, details, searches)

            ordered = sorted(rows[:2], key=row_key)
            descriptor["row_count"] = 2
            descriptor["prefix"] = ""
            with self.assertRaisesRegex(ValueError, "canonically ordered"):
                leaf_rows(
                    {"rows": list(reversed(ordered))},
                    descriptor,
                    "search",
                    1,
                    {},
                    [],
                )

    def test_discoverability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root, 2)
            _, rows, _ = load_source(source)
            details = {row["id"]: row for row in rows}
            searches = [
                (row["id"], word, compact_row(row))
                for row in rows
                for word in search_words(row["label"])
            ]
            check_search(details, searches)
            searches.pop()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                check_search(details, searches)

    def test_source_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root)
            index_path = source / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            asset = source / "candidates.jsonl.gz"
            rows = gzip.decompress(asset.read_bytes()).decode()
            payload = gzip.compress((rows + rows).encode(), mtime=0)
            asset.write_bytes(payload)
            index["assets"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
            index["assets"][0]["row_count"] *= 2
            index["coverage"]["qualified_candidates"] *= 2
            index_path.write_text(json.dumps(index), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicated"):
                load_source(source)

    def test_strict_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            build_pack(source_pack(root), output, RELEASE)
            index = json.loads((output / "index.json").read_text(encoding="utf-8"))
            changed = copy.deepcopy(index)
            changed["unexpected"] = True
            (output / "index.json").write_bytes(json_bytes(changed))

            with self.assertRaisesRegex(ValueError, "schema is invalid"):
                check_pack(output)

    def test_release_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_pack(root)
            with self.assertRaisesRegex(ValueError, "durable GitHub release"):
                build_pack(
                    source,
                    root / "public",
                    "https://api.github.com/actions/artifacts/123/zip",
                )


if __name__ == "__main__":
    unittest.main()
