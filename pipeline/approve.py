"""Approve declared-review candidates as isolated provisional records."""

from __future__ import annotations

from pathlib import Path

from retrieve import check_retrieval
from review import check_receipt
from support import base_id, validate_bundle
from synth import (
    KINDS,
    check_candidate,
    check_manifest,
    check_version,
    hash_value,
    require,
    valid_hash,
)


SCHEMA_VERSION = 1
DECISION = "accept-provisional"
RECORD_KEYS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "candidate_digest",
        "kind",
        "status",
        "decision",
        "generator_version",
        "corpus_digest",
        "retrieval_digest",
        "support_digest",
        "support_ids",
        "receipt_digest",
        "approval_digest",
    }
)


def approval_hash(value: dict) -> str:
    """Hash every immutable approval field except its own digest."""
    body = {key: value[key] for key in RECORD_KEYS - {"approval_digest"}}
    return hash_value(body)


def check_approval(value: object) -> dict:
    """Validate one exact, content-addressed provisional approval record."""
    require(
        isinstance(value, dict) and set(value) == RECORD_KEYS,
        "Approval record fields are invalid",
    )
    require(value["schema_version"] == SCHEMA_VERSION, "Schema version is invalid")
    require(value["kind"] in KINDS, "Approval kind is invalid")
    require(value["status"] == "provisional", "Approval status is invalid")
    require(value["decision"] == DECISION, "Approval decision is invalid")
    check_version(value["generator_version"])
    require(
        isinstance(value["candidate_id"], str)
        and value["candidate_id"].startswith(f"{value['kind']}:")
        and valid_hash(value["candidate_id"].partition(":")[2]),
        "Approval candidate ID is invalid",
    )
    for field in (
        "candidate_digest",
        "corpus_digest",
        "retrieval_digest",
        "support_digest",
        "receipt_digest",
        "approval_digest",
    ):
        require(valid_hash(value[field]), f"Approval {field} is invalid")
    identifiers = value["support_ids"]
    require(
        isinstance(identifiers, list) and bool(identifiers),
        "Approval support papers are empty",
    )
    canonical = [f"arxiv:{base_id(identifier)}" for identifier in identifiers]
    require(
        identifiers == sorted(set(canonical)),
        "Approval support-paper IDs are invalid",
    )
    require(
        value["approval_digest"] == approval_hash(value),
        "Approval digest does not match its record",
    )
    return value


def check_lineage(candidate: dict, support: dict) -> None:
    """Bind every support row to the candidate's exact promoted shard digest."""
    expected = {(row["source_id"], row["sha256"]) for row in candidate["source_hashes"]}
    actual = {
        (f"arxiv:{paper['archive']['month']}", paper["archive"]["sha256"])
        for paper in support["papers"]
    }
    require(actual == expected, "Support archive lineage does not match candidate")


def approve(
    candidate: dict,
    manifest: dict,
    receipt: dict,
    retrieval: dict,
    support: dict,
    *,
    archive_root: Path,
) -> dict:
    """Approve an exactly bound candidate without publishing claims or ontology."""
    check_manifest(manifest)
    check_candidate(candidate, manifest)
    check_receipt(receipt)
    check_retrieval(retrieval)
    require(isinstance(archive_root, Path), "Support archive root is required")
    validate_bundle(
        support,
        expected_digest=manifest["corpus_digest"],
        archive_root=archive_root,
    )
    check_lineage(candidate, support)

    require(
        candidate["review_status"] == "unreviewed",
        "Only an unreviewed candidate can be approved",
    )
    require(
        receipt["decision"] == DECISION,
        "Declared review did not approve candidate",
    )
    require(
        receipt["candidate_digest"] == candidate["candidate_digest"],
        "Review candidate digest does not match",
    )
    require(
        receipt["scope"]["corpus_digest"] == manifest["corpus_digest"],
        "Review corpus generation does not match",
    )
    require(
        retrieval["candidate_id"] == candidate["candidate_id"],
        "Retrieval candidate ID does not match",
    )
    require(
        retrieval["retrieval_corpus_digest"] == manifest["corpus_digest"],
        "Retrieval corpus generation does not match",
    )
    require(
        receipt["scope"]["retrieval_digest"] == retrieval["retrieval_digest"],
        "Review retrieval digest does not match",
    )

    expected_ids = candidate["support_ids"]
    actual_ids = [paper["canonical_id"] for paper in support["papers"]]
    require(actual_ids == expected_ids, "Review support-paper IDs do not match")

    record = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate["candidate_id"],
        "candidate_digest": candidate["candidate_digest"],
        "kind": candidate["kind"],
        "status": "provisional",
        "decision": DECISION,
        "generator_version": manifest["generator_version"],
        "corpus_digest": manifest["corpus_digest"],
        "retrieval_digest": retrieval["retrieval_digest"],
        "support_digest": support["content_sha256"],
        "support_ids": expected_ids,
        "receipt_digest": receipt["receipt_digest"],
    }
    record["approval_digest"] = approval_hash(record)
    return check_approval(record)
