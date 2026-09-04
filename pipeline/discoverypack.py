#!/usr/bin/env python3
"""Project a validated discovery artifact into a bounded public review queue."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from discover import ARTIFACT_KEYS, check_gate, check_related
from files import atomic_write_text
from privacy import unsafe_public
from synth import check_candidate, check_manifest


VERSION = "discovery-browser-1"
NOTICE = (
    "Machine-generated cross-paper combinations queued for human review. They are "
    "not screened briefs, recommendations, novelty findings, or feasibility "
    "assessments."
)
ROOT_KEYS = {
    "schema_version",
    "generator_version",
    "status",
    "source",
    "count",
    "review_gate",
    "notice",
    "candidates",
}
SOURCE_KEYS = {
    "run_id",
    "artifact_id",
    "artifact_sha256",
    "generator_version",
    "corpus_digest",
    "manifest_sha256",
    "manifest_papers",
    "loaded_papers",
    "skipped_outside",
}
ROW_KEYS = {"id", "digest", "review_status", "identity", "support_ids"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDEA_ID = re.compile(r"^idea:[0-9a-f]{64}$")
ARXIV_ID = re.compile(r"^arxiv:(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Invalid discovery browser queue: {message}")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_positive(value: object, field: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool) and value > 0,
        f"{field} is invalid",
    )
    return value


def make_browser(
    artifact: object,
    *,
    run_id: int,
    artifact_id: int,
    artifact_sha256: str,
) -> dict:
    """Validate a successful discovery result and retain only review-queue fields."""
    require(
        isinstance(artifact, dict) and set(artifact) == ARTIFACT_KEYS,
        "source artifact fields are stale",
    )
    require(
        artifact["schema_version"] == 1 and artifact["status"] == "provisional",
        "source artifact is not provisional",
    )
    manifest = check_manifest(artifact["corpus"])
    candidates = artifact["candidates"]
    require(
        isinstance(candidates, list) and 0 < len(candidates) <= 48, "count is invalid"
    )
    for candidate in candidates:
        check_candidate(candidate, manifest)
        require(
            candidate["kind"] == "idea" and candidate["review_status"] == "unreviewed",
            "a candidate crossed the review boundary",
        )
    check_related(artifact["related_work"], candidates)
    check_gate(artifact["review_gate"])

    coverage = artifact["coverage"]
    require(isinstance(coverage, dict), "coverage is invalid")
    manifest_papers = parse_positive(coverage.get("manifest_papers"), "manifest papers")
    loaded_papers = parse_positive(coverage.get("loaded_papers"), "loaded papers")
    skipped_outside = coverage.get("skipped_outside")
    require(
        isinstance(skipped_outside, int)
        and not isinstance(skipped_outside, bool)
        and skipped_outside >= 0
        and loaded_papers + skipped_outside == manifest_papers,
        "scope coverage is invalid",
    )
    require(bool(SHA256.fullmatch(artifact_sha256)), "artifact digest is invalid")

    rows = [
        {
            "id": candidate["candidate_id"],
            "digest": candidate["candidate_digest"],
            "review_status": "unreviewed",
            "identity": candidate["identity"],
            "support_ids": candidate["support_ids"],
        }
        for candidate in candidates
    ]
    rows.sort(key=lambda row: row["id"])
    return {
        "schema_version": 1,
        "generator_version": VERSION,
        "status": "provisional",
        "source": {
            "run_id": parse_positive(run_id, "run ID"),
            "artifact_id": parse_positive(artifact_id, "artifact ID"),
            "artifact_sha256": artifact_sha256,
            "generator_version": artifact["generator_version"],
            "corpus_digest": manifest["corpus_digest"],
            "manifest_sha256": coverage["manifest_sha256"],
            "manifest_papers": manifest_papers,
            "loaded_papers": loaded_papers,
            "skipped_outside": skipped_outside,
        },
        "count": len(rows),
        "review_gate": artifact["review_gate"],
        "notice": NOTICE,
        "candidates": rows,
    }


def check_browser(value: object) -> dict:
    """Strictly validate a public queue without upgrading its review state."""
    require(isinstance(value, dict) and set(value) == ROOT_KEYS, "fields are stale")
    require(
        value["schema_version"] == 1
        and value["generator_version"] == VERSION
        and value["status"] == "provisional"
        and value["notice"] == NOTICE,
        "version or status is invalid",
    )
    source = value["source"]
    require(
        isinstance(source, dict) and set(source) == SOURCE_KEYS, "source is invalid"
    )
    for field in ("run_id", "artifact_id", "manifest_papers", "loaded_papers"):
        parse_positive(source[field], field)
    require(
        isinstance(source["skipped_outside"], int)
        and not isinstance(source["skipped_outside"], bool)
        and source["skipped_outside"] >= 0
        and source["loaded_papers"] + source["skipped_outside"]
        == source["manifest_papers"],
        "coverage is invalid",
    )
    for field in ("artifact_sha256", "corpus_digest", "manifest_sha256"):
        require(
            isinstance(source[field], str) and bool(SHA256.fullmatch(source[field])),
            f"{field} is invalid",
        )
    require(source["generator_version"] == "discover-2", "source version is invalid")
    gate = value["review_gate"]
    check_gate(gate)
    rows = value["candidates"]
    require(
        isinstance(rows, list) and len(rows) == value["count"] and 0 < len(rows) <= 48,
        "candidate count is invalid",
    )
    ids = []
    for row in rows:
        require(
            isinstance(row, dict) and set(row) == ROW_KEYS, "candidate fields are stale"
        )
        require(
            isinstance(row["id"], str)
            and bool(IDEA_ID.fullmatch(row["id"]))
            and isinstance(row["digest"], str)
            and bool(SHA256.fullmatch(row["digest"]))
            and row["review_status"] == "unreviewed",
            "candidate identity or status is invalid",
        )
        identity = row["identity"]
        require(
            isinstance(identity, dict)
            and set(identity) == {"target", "intervention", "mechanism", "outcome"}
            and all(
                isinstance(text, str)
                and bool(text)
                and text == text.strip()
                and len(text) <= 240
                and not unsafe_public(text)
                for text in identity.values()
            ),
            "candidate description is invalid",
        )
        supports = row["support_ids"]
        require(
            isinstance(supports, list)
            and len(supports) >= 2
            and supports == sorted(set(supports))
            and all(
                isinstance(item, str) and ARXIV_ID.fullmatch(item) for item in supports
            ),
            "candidate supports are invalid",
        )
        ids.append(row["id"])
    require(
        ids == sorted(ids) and len(ids) == len(set(ids)), "candidate IDs are invalid"
    )
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--artifact-id", type=int)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.check:
        check_browser(json.loads(args.output.read_text(encoding="utf-8")))
        print("Validated provisional discovery browser queue")
        return
    require(args.input is not None, "--input is required")
    require(args.run_id is not None, "--run-id is required")
    require(args.artifact_id is not None, "--artifact-id is required")
    require(args.expected_sha256 is not None, "--expected-sha256 is required")
    actual_sha256 = file_hash(args.input)
    require(actual_sha256 == args.expected_sha256, "source artifact digest disagrees")
    artifact = json.loads(args.input.read_text(encoding="utf-8"))
    value = make_browser(
        artifact,
        run_id=args.run_id,
        artifact_id=args.artifact_id,
        artifact_sha256=actual_sha256,
    )
    check_browser(value)
    atomic_write_text(
        args.output,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"Packed {value['count']} unreviewed candidates")


if __name__ == "__main__":
    main()
