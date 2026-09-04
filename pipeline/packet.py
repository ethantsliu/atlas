"""Build immutable, explicitly unreviewed full-corpus idea triage packets."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from approve import check_lineage
from retrieve import check_retrieval
from support import validate_bundle
from synth import check_candidate, check_manifest, hash_value, require


ROOT = Path(__file__).resolve().parents[1]
PACKET_SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/packet.schema.json").read_text(encoding="utf-8"))
)
SCHEMA_VERSION = 1
PACKET_KIND = "full-corpus-idea-triage"
PENDING = "pending-human-review"
MIN_SUPPORTS = 6
MIN_RETRIEVAL_CANDIDATES = 5
CHECKLIST_FIELDS = (
    "support_mechanism_relevance",
    "identity_distinctness",
    "experimental_testability",
    "retrieval_inspected",
    "no_novelty_claim",
)


def packet_digest(value: dict) -> str:
    """Hash every packet field except its self-describing digest."""
    return hash_value(
        {key: item for key, item in value.items() if key != "packet_digest"}
    )


def validate_schema(value: object) -> None:
    """Raise the first strict packet-schema error with a stable field path."""
    errors = sorted(
        PACKET_SCHEMA.iter_errors(value), key=lambda error: list(error.absolute_path)
    )
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise ValueError(f"Triage packet schema violation at {location}: {error.message}")


def validate_inputs(
    candidate: dict,
    manifest: dict,
    retrieval: dict,
    support: dict,
    *,
    archive_root: Path,
) -> None:
    """Validate and cross-bind every source artifact used by one packet."""
    check_manifest(manifest)
    check_candidate(candidate, manifest)
    check_retrieval(retrieval)
    require(isinstance(archive_root, Path), "Support archive root is required")
    validate_bundle(
        support,
        expected_digest=manifest["corpus_digest"],
        archive_root=archive_root,
    )
    check_lineage(candidate, support)

    require(candidate["kind"] == "idea", "Triage packet requires an idea candidate")
    require(
        candidate["review_status"] == "unreviewed",
        "Triage packet requires an unreviewed candidate",
    )
    support_ids = [paper["canonical_id"] for paper in support["papers"]]
    require(
        len(support_ids) >= MIN_SUPPORTS,
        f"Triage packet requires at least {MIN_SUPPORTS} resolvable supports",
    )
    require(
        support_ids == candidate["support_ids"],
        "Triage packet support-paper IDs do not match candidate",
    )
    require(
        retrieval["candidate_id"] == candidate["candidate_id"],
        "Triage packet retrieval candidate ID does not match",
    )
    require(
        retrieval["retrieval_corpus_digest"] == manifest["corpus_digest"],
        "Triage packet retrieval corpus digest does not match",
    )
    retrieval_ids = [row["canonical_id"] for row in retrieval["candidates"]]
    require(
        len(retrieval_ids) >= MIN_RETRIEVAL_CANDIDATES,
        "Triage packet requires at least "
        f"{MIN_RETRIEVAL_CANDIDATES} retrieval candidates",
    )
    require(
        set(retrieval_ids).isdisjoint(support_ids),
        "Triage packet retrieval candidates overlap support papers",
    )


def packet_value(
    candidate: dict, manifest: dict, retrieval: dict, support: dict
) -> dict:
    """Project validated source artifacts onto the immutable packet boundary."""
    value = {
        "schema_version": SCHEMA_VERSION,
        "packet_kind": PACKET_KIND,
        "status": "unreviewed",
        "candidate": {
            "candidate_id": candidate["candidate_id"],
            "candidate_digest": candidate["candidate_digest"],
            "identity": copy.deepcopy(candidate["identity"]),
        },
        "lineage": {
            "corpus_digest": manifest["corpus_digest"],
            "candidate_digest": candidate["candidate_digest"],
            "retrieval_digest": retrieval["retrieval_digest"],
            "support_digest": support["content_sha256"],
        },
        "support_papers": copy.deepcopy(support["papers"]),
        "retrieval_candidates": copy.deepcopy(retrieval["candidates"]),
        "checklist": {field: PENDING for field in CHECKLIST_FIELDS},
        "review_gate": {
            "automatic_promotion": False,
            "required_receipt": "separate-declared-human-receipt",
        },
    }
    value["packet_digest"] = packet_digest(value)
    return value


def make_triage_packet(
    candidate: dict,
    manifest: dict,
    retrieval: dict,
    support: dict,
    *,
    archive_root: Path,
) -> dict:
    """Build one evidence packet that cannot represent human review or approval."""
    validate_inputs(
        candidate,
        manifest,
        retrieval,
        support,
        archive_root=archive_root,
    )
    value = packet_value(candidate, manifest, retrieval, support)
    validate_schema(value)
    return value


def check_triage_packet(
    value: object,
    candidate: dict,
    manifest: dict,
    retrieval: dict,
    support: dict,
    *,
    archive_root: Path,
) -> dict:
    """Verify an existing packet against exact source artifacts and archive rows."""
    validate_schema(value)
    validate_inputs(
        candidate,
        manifest,
        retrieval,
        support,
        archive_root=archive_root,
    )
    require(isinstance(value, dict), "Triage packet must be an object")
    require(
        value["packet_digest"] == packet_digest(value),
        "Triage packet digest does not match its content",
    )
    require(
        value == packet_value(candidate, manifest, retrieval, support),
        "Triage packet does not match its source artifacts",
    )
    return value
