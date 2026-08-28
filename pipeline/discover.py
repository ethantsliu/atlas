#!/usr/bin/env python3
"""Build and verify provisional discovery candidates from promoted corpus shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from archive import MANIFEST_NAME, read_manifest
from candidate import check_candidates as check_tricks
from files import atomic_write_text
from retrieve import check_retrieval
from scan import check_trick_sources, scan_archive
from synth import check_candidate, check_manifest, make_manifest


VERSION = "discover-2"
MAX_IDEAS = 48
ARTIFACT_KEYS = {
    "schema_version",
    "generator_version",
    "status",
    "corpus",
    "coverage",
    "trick_candidates",
    "candidates",
    "related_work",
    "review_gate",
}
GATE_KEYS = {"automatic_promotion", "required_receipt", "note"}
COVERAGE_KEYS = {
    "manifest_sha256",
    "manifest_papers",
    "loaded_papers",
    "recovered_outside",
    "skipped_outside",
    "manifest_months",
    "loaded_months",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MONTH = re.compile(r"^\d{4}-\d{2}$")


def parse_args() -> argparse.Namespace:
    """Parse one build or verification request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--limit", type=int, default=48)
    return parser.parse_args()


def file_hash(path: Path) -> str:
    """Hash one promoted source artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_rows(manifest: dict) -> list[dict[str, str]]:
    """Project corpus shards into synthesis provenance rows."""
    return [
        {
            "source_id": f"arxiv:{row['month']}",
            "sha256": row["sha256"],
        }
        for row in manifest["shards"]
    ]


def build_artifact(root: Path, limit: int) -> dict | None:
    """Build one deterministic provisional discovery artifact."""
    index_path = root / MANIFEST_NAME
    if not index_path.is_file():
        return None
    manifest = read_manifest(root)
    sources = source_rows(manifest)
    if not sources:
        return None
    corpus = make_manifest(VERSION, sources)
    scan = scan_archive(root, manifest, corpus, limit)
    return {
        "schema_version": 1,
        "generator_version": VERSION,
        "status": "provisional",
        "corpus": corpus,
        "coverage": {
            "manifest_sha256": file_hash(index_path),
            "manifest_papers": manifest.get("counts", {}).get("all", 0),
            "loaded_papers": scan["loaded_papers"],
            "recovered_outside": scan["recovered_outside"],
            "skipped_outside": scan["skipped_outside"],
            "manifest_months": len(manifest["shards"]),
            "loaded_months": scan["loaded_months"],
        },
        "trick_candidates": scan["trick_candidates"],
        "candidates": scan["candidates"],
        "related_work": scan["related_work"],
        "review_gate": {
            "automatic_promotion": False,
            "required_receipt": "declared-human-review",
            "note": (
                "Promotion requires a declared review receipt bound to the candidate "
                "digest; this receipt is not authenticated human proof, and provenance "
                "hashes are not related-work evidence."
            ),
        },
    }


def check_related(related: object, candidates: list[dict]) -> None:
    """Validate candidate-only queues without inferring research claims."""
    candidate_rows = {row["candidate_id"]: row for row in candidates}
    if not isinstance(related, dict) or set(related) != set(candidate_rows):
        raise ValueError("Discovery related-work queues are incomplete")
    corpus_digests = set()
    for candidate_id, result in related.items():
        check_retrieval(result)
        if result["candidate_id"] != candidate_id:
            raise ValueError("Discovery related-work queue is invalid")
        corpus_digests.add(result["retrieval_corpus_digest"])
        supports = set(candidate_rows[candidate_id]["support_ids"])
        rows = result["candidates"]
        if len(rows) > 12 or any(row["canonical_id"] in supports for row in rows):
            raise ValueError("Discovery related-work ranking is invalid")
    if len(corpus_digests) > 1:
        raise ValueError("Discovery related-work corpus digests disagree")


def check_gate(gate: object) -> None:
    """Require one exact declared-review promotion boundary."""
    note = (
        "Promotion requires a declared review receipt bound to the candidate "
        "digest; this receipt is not authenticated human proof, and provenance "
        "hashes are not related-work evidence."
    )
    if (
        not isinstance(gate, dict)
        or set(gate) != GATE_KEYS
        or gate.get("automatic_promotion") is not False
        or gate.get("required_receipt") != "declared-human-review"
        or gate.get("note") != note
    ):
        raise ValueError("Discovery review gate is invalid")


def check_coverage(value: object, corpus: dict) -> None:
    """Validate bounded coverage metadata against the corpus manifest."""
    if not isinstance(value, dict) or set(value) != COVERAGE_KEYS:
        raise ValueError("Discovery coverage fields are invalid")
    counts = (
        value["manifest_papers"],
        value["loaded_papers"],
        value["recovered_outside"],
        value["skipped_outside"],
        value["manifest_months"],
    )
    source_months = [
        row["source_id"].removeprefix("arxiv:") for row in corpus["source_hashes"]
    ]
    loaded = value["loaded_months"]
    if (
        not SHA256.fullmatch(str(value["manifest_sha256"]))
        or not all(
            isinstance(count, int) and not isinstance(count, bool) for count in counts
        )
        or not 0 <= value["loaded_papers"] <= value["manifest_papers"]
        or not 0 <= value["recovered_outside"] <= value["loaded_papers"]
        or not 0 <= value["skipped_outside"] <= value["manifest_papers"]
        or value["loaded_papers"] + value["skipped_outside"] > value["manifest_papers"]
        or value["manifest_months"] != len(source_months)
        or not isinstance(loaded, list)
        or loaded != sorted(set(loaded))
        or not all(
            isinstance(month, str) and MONTH.fullmatch(month) for month in loaded
        )
        or not set(loaded) <= set(source_months)
    ):
        raise ValueError("Discovery coverage is invalid")


def check_artifact(value: object, archive_root: Path) -> dict:
    """Validate provenance, review state, and artifact references."""
    if not isinstance(archive_root, Path):
        raise ValueError("Discovery archive root is required")
    if not isinstance(value, dict) or set(value) != ARTIFACT_KEYS:
        raise ValueError("Discovery artifact fields are invalid")
    if (
        value["schema_version"] != 1
        or value["generator_version"] != VERSION
        or value["status"] != "provisional"
    ):
        raise ValueError("Discovery artifact version or status is invalid")
    corpus = check_manifest(value["corpus"])
    candidates = value["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("Discovery candidates are invalid")
    for candidate in candidates:
        check_candidate(candidate, corpus)
        if candidate["review_status"] != "unreviewed":
            raise ValueError("Discovery candidate bypassed declared review")
    candidate_ids = [candidate["candidate_id"] for candidate in candidates]
    if len(candidate_ids) > MAX_IDEAS or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Discovery candidates are duplicated")
    check_related(value["related_work"], candidates)
    tricks = value["trick_candidates"]
    check_tricks(tricks)
    if len(tricks) > 200:
        raise ValueError("Discovery trick candidates exceed their bounded queue")
    check_coverage(value["coverage"], corpus)
    archive = read_manifest(archive_root)
    if source_rows(archive) != corpus["source_hashes"]:
        raise ValueError("Discovery corpus manifest does not match its archive")
    if file_hash(archive_root / MANIFEST_NAME) != value["coverage"]["manifest_sha256"]:
        raise ValueError("Discovery archive manifest digest does not match")
    loaded = set(value["coverage"]["loaded_months"])
    rows = [row for row in archive["shards"] if row["month"] in loaded]
    loaded_all = sum(row["counts"]["all"] for row in rows)
    loaded_outside = sum(row["counts"]["outside"] for row in rows)
    if (
        value["coverage"]["loaded_papers"] + value["coverage"]["skipped_outside"]
        != loaded_all
        or value["coverage"]["recovered_outside"] + value["coverage"]["skipped_outside"]
        != loaded_outside
    ):
        raise ValueError("Discovery recovery coverage is invalid")
    check_trick_sources(archive_root, archive, tricks)
    check_gate(value["review_gate"])
    return value


def main() -> None:
    """Build or independently verify one candidate artifact."""
    args = parse_args()
    if args.check:
        if args.archive is None:
            raise SystemExit("--archive is required when checking candidates")
        value = json.loads(args.output.read_text(encoding="utf-8"))
        check_artifact(value, args.archive)
        print(f"Validated {len(value['candidates']):,} provisional candidates")
        return
    if args.archive is None:
        raise SystemExit("--archive is required when building candidates")
    value = build_artifact(args.archive, args.limit)
    if value is None:
        print("No promoted corpus is available; discovery has no work")
        return
    check_artifact(value, args.archive)
    atomic_write_text(
        args.output,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"Built {len(value['candidates']):,} provisional candidates")


if __name__ == "__main__":
    main()
