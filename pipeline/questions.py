#!/usr/bin/env python3
"""Project full-corpus directions into provenance-bound research questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from catalogproof import (
    VERSION as CATALOG_VERSION,
    canonical_hash,
    check_archive_supports,
    check_catalog,
)
from files import atomic_write_text


ROOT = Path(__file__).resolve().parents[1]
VERSION = "questions-1"
IDENTITY_VERSION = "direction-question-1"
TEMPLATE_VERSION = "comparative-conditions-1"
STATUS = "corpus-derived-unreviewed-candidate"
EVIDENCE_RELATION = (
    "The references establish only corpus co-occurrence between this arXiv subject "
    "and curated technique family; they do not establish novelty, causality, "
    "feasibility, or effectiveness."
)
NOTICE = (
    "These are automatically projected research-question candidates, not reviewed "
    "ideas, recommendations, novelty findings, or feasibility assessments. The "
    "reviewed Atlas idea collection remains separate."
)
SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/questions.schema.json").read_text(encoding="utf-8"))
)


def parse_args() -> argparse.Namespace:
    """Parse one question-artifact build or validation request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def question_id(subject: str, technique: str) -> str:
    """Return a corpus-independent identity for one crossover question."""
    body = {
        "identity_version": IDENTITY_VERSION,
        "subject_id": subject,
        "technique_id": technique,
    }
    return f"question:{canonical_hash(body)}"


def policy_contract() -> dict:
    """Commit to the exact projection semantics, not mutable source counts."""
    body = {
        "identity_version": IDENTITY_VERSION,
        "template_version": TEMPLATE_VERSION,
        "candidate_per_direction": 1,
        "review_status": "unreviewed",
        "novelty_status": "not-assessed",
        "feasibility_status": "not-assessed",
        "evidence_relation": EVIDENCE_RELATION,
    }
    return {"digest": canonical_hash(body), **body}


def question_text(subject: str, technique: str) -> str:
    """Render a neutral comparative question without predicting an effect."""
    return (
        f"Across research classified under {subject}, under which documented "
        f"conditions is {technique} associated with better, worse, or unchanged "
        "reported outcomes?"
    )


def candidate_row(direction: dict, techniques: dict[str, str], rank: int) -> dict:
    """Project one validated direction without weakening its source evidence."""
    subject = direction["subject_id"]
    technique = direction["technique_id"]
    label = techniques[technique]
    return {
        "id": question_id(subject, technique),
        "candidate_kind": "research-question",
        "status": STATUS,
        "review_status": "unreviewed",
        "novelty_status": "not-assessed",
        "feasibility_status": "not-assessed",
        "rank": rank,
        "identity": {
            "subject_id": subject,
            "technique_id": technique,
        },
        "question": question_text(subject, label),
        "source_direction": {
            "id": direction["id"],
            "support_count": direction["support_count"],
            "year_count": direction["year_count"],
            "independent_author_groups_at_least": direction[
                "independent_author_groups_at_least"
            ],
            "npmi": direction["npmi"],
        },
        "support_ids": [*direction["support_ids"]],
        "support_refs": [dict(row) for row in direction["support_refs"]],
        "evidence_relation": EVIDENCE_RELATION,
    }


def artifact_hash(value: dict) -> str:
    """Hash every artifact field except its self-describing digest."""
    return canonical_hash(
        {key: item for key, item in value.items() if key != "content_sha256"}
    )


def validate_schema(value: object) -> None:
    """Raise the first deterministic schema error."""
    errors = sorted(SCHEMA.iter_errors(value), key=lambda error: list(error.path))
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise ValueError(
        f"Question artifact schema violation at {location}: {error.message}"
    )


def build_artifact(catalog: dict) -> dict:
    """Build one unreviewed question for every published catalog direction."""
    check_catalog(catalog)
    if catalog["generator_version"] != CATALOG_VERSION:
        raise ValueError("Questions require the exact-support catalog generation")
    techniques = {row["id"]: row["label"] for row in catalog["techniques"]}
    candidates = [
        candidate_row(direction, techniques, rank)
        for rank, direction in enumerate(catalog["directions"], 1)
    ]
    result = {
        "schema_version": 1,
        "generator_version": VERSION,
        "status": "corpus-derived-unreviewed-candidates",
        "source_catalog": {
            "content_sha256": catalog["content_sha256"],
            "generator_version": catalog["generator_version"],
            "corpus_manifest_sha256": catalog["corpus"]["manifest_sha256"],
            "source_papers": catalog["corpus"]["source_count"],
            "source_directions": len(catalog["directions"]),
        },
        "policy": policy_contract(),
        "counts": {
            "source_directions": len(catalog["directions"]),
            "unreviewed_candidate_questions": len(candidates),
            "reviewed_ideas_added": 0,
        },
        "candidates": candidates,
        "notice": NOTICE,
    }
    result["content_sha256"] = artifact_hash(result)
    validate_schema(result)
    return result


def check_artifact(value: object, catalog: dict, archive: Path | None = None) -> dict:
    """Recompute the projection and optionally resolve every archive support."""
    validate_schema(value)
    if not isinstance(value, dict):
        raise ValueError("Question artifact must be an object")
    if value.get("content_sha256") != artifact_hash(value):
        raise ValueError("Question artifact content digest is invalid")
    expected = build_artifact(catalog)
    if value != expected:
        raise ValueError("Question artifact does not match its source catalog")
    if archive is not None:
        check_archive_supports(catalog, archive)
    return value


def read_json(path: Path, label: str) -> dict:
    """Read one required JSON object with a concise error boundary."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} JSON is invalid") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def main() -> None:
    """Build or validate the full-catalog question projection."""
    args = parse_args()
    catalog = read_json(args.catalog, "Catalog")
    if args.check:
        value = read_json(args.output, "Question artifact")
        check_artifact(value, catalog, args.archive)
        print(f"Validated {len(value['candidates']):,} unreviewed candidates")
        return
    value = build_artifact(catalog)
    atomic_write_text(
        args.output,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"Built {len(value['candidates']):,} unreviewed candidates")


if __name__ == "__main__":
    main()
