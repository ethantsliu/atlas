#!/usr/bin/env python3
"""Package validated method candidates as bounded, lazy browser assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from files import atomic_write_bytes
from methods import INDEX_SCHEMA, check_candidate, iter_candidates
from methodtree import (
    GENERATOR,
    STATUS,
    Limits,
    MAX_PACKAGE_BYTES,
    PackageTooLarge,
    Store,
    build_details,
    build_search,
    compact_row,
    fits,
    json_bytes,
    summary_value,
)
from methodcatalog import build_catalog_details, build_catalog_search, identity_row


ROOT = Path(__file__).resolve().parents[1]
INDEX_RAW = 8 * 1024
INDEX_GZIP = 3 * 1024
SUMMARY_RAW = 32 * 1024
SUMMARY_GZIP = 10 * 1024
TOP_RAW = 128 * 1024
TOP_GZIP = 32 * 1024
TOP_COUNT = 200
RELEASE_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/"
    r"download/[A-Za-z0-9][A-Za-z0-9._-]{0,99}/"
    r"candidates(?:-[0-9a-f]{64})?\.jsonl\.gz$"
)
PUBLIC_SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/methodpack.schema.json").read_text(encoding="utf-8"))
)


def parse_args() -> argparse.Namespace:
    """Parse one deterministic browser packaging or validation request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-url")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def file_hash(path: Path) -> str:
    """Hash one source asset without copying it into the public package."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def schema_check(value: object, label: str) -> None:
    """Require one value to match a strict public asset schema variant."""
    errors = sorted(
        PUBLIC_SCHEMA.iter_errors(value), key=lambda error: list(error.path)
    )
    if errors:
        raise ValueError(f"{label} schema is invalid: {errors[0].message}")


def load_source(source: Path) -> tuple[dict, list[dict], Path]:
    """Read a structurally valid, hashed, canonically ordered method artifact."""
    try:
        index = json.loads((source / "index.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Validated method source index is invalid") from error
    errors = sorted(INDEX_SCHEMA.iter_errors(index), key=lambda error: list(error.path))
    if errors:
        raise ValueError(
            f"Validated method source schema is invalid: {errors[0].message}"
        )
    asset = index["assets"][0]
    path = source / asset["path"]
    if not path.is_file() or file_hash(path) != asset["sha256"]:
        raise ValueError("Validated method source asset is missing or drifted")
    minimum = index["extraction"]["minimum_support"]
    rows: list[dict] = []
    identities: set[str] = set()
    prior = None
    for row in iter_candidates(path):
        key = check_candidate(row, minimum)
        if prior is not None and key < prior:
            raise ValueError("Validated method source is not canonically ordered")
        if row["id"] in identities:
            raise ValueError("Validated method source candidates are duplicated")
        identities.add(row["id"])
        rows.append(row)
        prior = key
    expected = index["coverage"]["qualified_candidates"]
    if len(rows) != expected or len(rows) != asset["row_count"]:
        raise ValueError("Validated method source row counts disagree")
    return index, rows, path


def fixed_asset(
    store: Store,
    stem: str,
    value: dict,
    rows: int,
    raw_cap: int,
    gzip_cap: int,
) -> dict:
    """Publish one fixed-size-addressed JSON asset after enforcing both caps."""
    content = json_bytes(value)
    if not fits(content, raw_cap, gzip_cap):
        raise ValueError(f"{stem.title()} asset exceeds its browser byte cap")
    return store.write(stem, value, rows)


def index_value(
    source: dict,
    summary: dict,
    top: dict,
    search: dict,
    details: dict,
    full: dict,
    tier: str,
) -> dict:
    """Create the tiny stable entry point without embedding candidate rows."""
    return {
        "schema_version": 1,
        "generator_version": GENERATOR,
        "status": STATUS,
        "tier": tier,
        "corpus": source["corpus"],
        "extraction": source["extraction"],
        "coverage": source["coverage"],
        "curated_families": source["curated_families"],
        "assets": {
            "summary": summary,
            "top": top,
            "search": search,
            "details": details,
            "download": full,
        },
        "notice": (
            source["notice"]
            if tier == "full-evidence"
            else source["notice"].rstrip()
            + " Evidence spans are available only in the immutable full release download."
        ),
    }


def output_ready(output: Path) -> None:
    """Require a fresh regular output directory to avoid mixed releases."""
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Method browser output must be a regular directory")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Method browser output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)


def build_pack(
    source_root: Path,
    output: Path,
    release_url: str,
    limits: Limits | None = None,
    package_cap: int = MAX_PACKAGE_BYTES,
) -> dict:
    """Build all lazy browser assets from one validated candidate artifact."""
    if not isinstance(release_url, str) or not RELEASE_URL.fullmatch(release_url):
        raise ValueError("Method full download must be a durable GitHub release URL")
    source, rows, source_asset = load_source(source_root)
    if package_cap <= INDEX_RAW:
        raise ValueError("Method browser package cap is too small")
    limits = limits or Limits()
    output_ready(output)
    output.rmdir()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output.parent, prefix=f".{output.name}-"
    ) as temporary:
        staging = Path(temporary)
        try:
            value = _build_tier(
                source,
                rows,
                source_asset,
                staging,
                release_url,
                limits,
                package_cap,
                "full-evidence",
            )
        except PackageTooLarge:
            shutil.rmtree(staging)
            staging.mkdir()
            value = _build_tier(
                source,
                rows,
                source_asset,
                staging,
                release_url,
                limits,
                package_cap,
                "catalog-only",
            )
        os.replace(staging, output)
    return value


def _build_tier(
    source: dict,
    rows: list[dict],
    source_asset: Path,
    output: Path,
    release_url: str,
    limits: Limits,
    package_cap: int,
    tier: str,
) -> dict:
    """Build and verify one complete browser tier in a private staging tree."""
    store = Store(output, package_cap - INDEX_RAW)
    full_sha = source["assets"][0]["sha256"]
    summary_body = summary_value(source, rows)
    schema_check(summary_body, "Method summary")
    summary = fixed_asset(store, "summary", summary_body, 1, SUMMARY_RAW, SUMMARY_GZIP)
    top_body = {
        "schema_version": 1,
        "corpus_manifest_sha256": source["corpus"]["manifest_sha256"],
        "order": "support-desc-label-asc-head-asc",
    }
    if tier == "catalog-only":
        top_body["full_asset_sha256"] = full_sha
        top_body["rows"] = [
            identity_row(row, ordinal) for ordinal, row in enumerate(rows[:TOP_COUNT])
        ]
    else:
        top_body["rows"] = [compact_row(row) for row in rows[:TOP_COUNT]]
    schema_check(top_body, "Method top")
    top = fixed_asset(store, "top", top_body, len(top_body["rows"]), TOP_RAW, TOP_GZIP)
    corpus = source["corpus"]["manifest_sha256"]
    if tier == "full-evidence":
        search = build_search(store, corpus, rows, limits)
        details = build_details(store, corpus, rows, limits)
    else:
        search = build_catalog_search(store, corpus, full_sha, rows, limits)
        details = build_catalog_details(store, corpus, full_sha, rows, limits)
    full = {
        "url": release_url,
        "encoding": "jsonl+gzip",
        "sha256": full_sha,
        "bytes": source_asset.stat().st_size,
        "row_count": len(rows),
    }
    value = index_value(source, summary, top, search, details, full, tier)
    schema_check(value, "Method browser index")
    content = json_bytes(value)
    if not fits(content, INDEX_RAW, INDEX_GZIP):
        raise ValueError("Method browser index exceeds its byte cap")
    if store.total_bytes + len(content) > package_cap:
        raise PackageTooLarge(
            "Method browser package exceeds the 100 MiB Pages boundary"
        )
    atomic_write_bytes(output / "index.json", content)
    from methodcheck import check_pack

    check_pack(output, limits=limits)
    return value


def main() -> None:
    """Build or strictly check one browser method asset package."""
    args = parse_args()
    if args.check:
        from methodcheck import check_pack

        value = check_pack(args.output)
        print(
            f"Validated {value['coverage']['qualified_candidates']:,} browser candidates"
        )
        return
    if args.input is None or args.release_url is None:
        raise SystemExit("--input and --release-url are required when building")
    value = build_pack(args.input, args.output, args.release_url)
    print(f"Packed {value['coverage']['qualified_candidates']:,} browser candidates")


if __name__ == "__main__":
    main()
