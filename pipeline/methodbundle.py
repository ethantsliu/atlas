#!/usr/bin/env python3
"""Create and safely restore a bounded durable browser-method release bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from bundle import unpack_tree
from files import atomic_write_bytes
from methodcheck import check_pack
from methodtree import GENERATOR, json_bytes


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 100_000
RECEIPT = Draft202012Validator(
    json.loads((ROOT / "schemas/methodbundle.schema.json").read_text(encoding="utf-8"))
)


def parse_args() -> argparse.Namespace:
    """Parse one bundle pack, check, or safe-unpack request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--unpack", action="store_true")
    return parser.parse_args()


def file_hash(path: Path) -> str:
    """Hash one release file in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def receipt_check(value: object) -> dict:
    """Validate one strict immutable release receipt."""
    errors = sorted(RECEIPT.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"Method browser receipt is invalid: {errors[0].message}")
    assert isinstance(value, dict)
    return value


def tree_stats(root: Path) -> tuple[list[Path], int]:
    """Return sorted regular assets after enforcing the release-size boundary."""
    paths = sorted(root.iterdir(), key=lambda path: path.name)
    if (
        not paths
        or len(paths) > MAX_FILES
        or any(path.is_symlink() or not path.is_file() for path in paths)
    ):
        raise ValueError("Method browser package contains unsafe or excessive entries")
    size = sum(path.stat().st_size for path in paths)
    if size > MAX_BYTES:
        raise ValueError("Method browser package exceeds the 100 MiB Pages boundary")
    return paths, size


def tar_bytes(root: Path, paths: list[Path], destination: Path) -> None:
    """Write a byte-deterministic gzip tar containing only normalized files."""
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=".methods-browser-", suffix=".tar.gz"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0
            ) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|") as archive:
                    for path in paths:
                        info = tarfile.TarInfo(path.name)
                        info.size = path.stat().st_size
                        info.mode = 0o644
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        with path.open("rb") as source:
                            archive.addfile(info, source)
            raw.flush()
            os.fsync(raw.fileno())
        if temporary.stat().st_size > MAX_BYTES:
            raise ValueError(
                "Method browser archive exceeds the 100 MiB release boundary"
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def pack_bundle(source: Path, output: Path) -> dict:
    """Verify and package same-origin assets with a content-addressed receipt."""
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Method release output directory must be empty")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Method release output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    index = check_pack(source)
    paths, unpacked = tree_stats(source)
    draft = output / "browser.tar.gz"
    tar_bytes(source, paths, draft)
    digest = file_hash(draft)
    archive = output / f"browser-{digest}.tar.gz"
    draft.replace(archive)
    index_content = (source / "index.json").read_bytes()
    download = index["assets"]["download"]
    candidate_name = Path(urlparse(download["url"]).path).name
    value = {
        "schema_version": 1,
        "generator_version": GENERATOR,
        "status": "validated-browser-package",
        "tier": index["tier"],
        "corpus": index["corpus"],
        "browser": {
            "path": archive.name,
            "encoding": "tar+gzip",
            "sha256": digest,
            "bytes": archive.stat().st_size,
            "file_count": len(paths),
            "unpacked_bytes": unpacked,
            "index_sha256": hashlib.sha256(index_content).hexdigest(),
        },
        "candidates": {
            "path": candidate_name,
            "encoding": download["encoding"],
            "sha256": download["sha256"],
            "bytes": download["bytes"],
            "row_count": download["row_count"],
        },
    }
    receipt_check(value)
    atomic_write_bytes(output / "browser.json", json_bytes(value))
    return value


def load_receipt(path: Path) -> dict:
    """Read a canonically encoded method browser release receipt."""
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Method browser release receipt cannot be read") from error
    if content != json_bytes(value):
        raise ValueError("Method browser release receipt is not canonical")
    return receipt_check(value)


def unpack_bundle(receipt: Path, archive: Path, output: Path) -> dict:
    """Verify, safely unpack, and revalidate a same-origin browser package."""
    value = load_receipt(receipt)
    expected = value["browser"]
    if (
        archive.name != expected["path"]
        or archive.is_symlink()
        or not archive.is_file()
        or archive.stat().st_size != expected["bytes"]
        or archive.stat().st_size > MAX_BYTES
        or file_hash(archive) != expected["sha256"]
    ):
        raise ValueError("Method browser release archive is missing or drifted")
    unpack_tree(archive, output, MAX_FILES, MAX_BYTES)
    try:
        index = check_pack(output)
        paths, unpacked = tree_stats(output)
        download = index["assets"]["download"]
        candidate = value["candidates"]
        download_fields = {
            key: download[key] for key in ("encoding", "sha256", "bytes", "row_count")
        }
        receipt_fields = {
            key: candidate[key] for key in ("encoding", "sha256", "bytes", "row_count")
        }
        valid = (
            len(paths) == expected["file_count"]
            and unpacked == expected["unpacked_bytes"]
            and file_hash(output / "index.json") == expected["index_sha256"]
            and index["corpus"] == value["corpus"]
            and index["tier"] == value["tier"]
            and Path(urlparse(download["url"]).path).name == candidate["path"]
            and download_fields == receipt_fields
        )
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise
    if not valid:
        shutil.rmtree(output, ignore_errors=True)
        raise ValueError("Method browser release receipt does not bind restored assets")
    return value


def main() -> None:
    """Build or restore one verified methods browser release bundle."""
    args = parse_args()
    if args.unpack:
        if args.receipt is None or args.archive is None:
            raise SystemExit("--receipt and --archive are required with --unpack")
        value = unpack_bundle(args.receipt, args.archive, args.output)
        print(f"Restored {value['candidates']['row_count']:,} browser candidates")
        return
    if args.source is None:
        raise SystemExit("--source is required when packaging")
    value = pack_bundle(args.source, args.output)
    print(f"Packaged {value['candidates']['row_count']:,} browser candidates")


if __name__ == "__main__":
    main()
