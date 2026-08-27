"""Strict declared-review receipts for synthesized candidate revisions."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from synth import hash_value, require, valid_hash


SCHEMA_VERSION = 1
DECISIONS = frozenset({"accept-provisional", "hold", "reject"})
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "candidate_digest",
        "decision",
        "reviewer_mode",
        "reviewer_id",
        "checked_at",
        "scope",
        "receipt_digest",
    }
)
SCOPE_KEYS = frozenset({"corpus_digest", "retrieval_digest"})
REVIEWER = re.compile(r"^reviewer:[0-9a-f]{64}$")
UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def valid_reviewer(value: object) -> bool:
    """Accept only an opaque non-PII reviewer token."""
    return isinstance(value, str) and bool(REVIEWER.fullmatch(value))


def valid_time(value: object) -> bool:
    """Accept a real second-precision timestamp in canonical UTC form."""
    if not isinstance(value, str) or not UTC_TIME.fullmatch(value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def check_scope(value: object) -> None:
    """Require exact digest commitments for corpus and retrieval scope."""
    require(
        isinstance(value, dict) and set(value) == SCOPE_KEYS,
        "Review scope fields are invalid",
    )
    require(
        valid_hash(value["corpus_digest"]) and valid_hash(value["retrieval_digest"]),
        "Review scope digests are invalid",
    )


def receipt_hash(value: dict) -> str:
    """Hash every immutable receipt field except its own digest."""
    body = {key: value[key] for key in RECEIPT_KEYS - {"receipt_digest"}}
    return hash_value(body)


def make_receipt(
    *,
    candidate_digest: str,
    decision: str,
    reviewer_id: str,
    checked_at: str,
    corpus_digest: str,
    retrieval_digest: str,
) -> dict:
    """Build one content-addressed declared-review receipt."""
    require(valid_hash(candidate_digest), "Candidate digest is invalid")
    require(decision in DECISIONS, "Review decision is invalid")
    require(valid_reviewer(reviewer_id), "Reviewer ID is not opaque")
    require(valid_time(checked_at), "Review timestamp is invalid")
    scope = {
        "corpus_digest": corpus_digest,
        "retrieval_digest": retrieval_digest,
    }
    check_scope(scope)
    value = {
        "schema_version": SCHEMA_VERSION,
        "candidate_digest": candidate_digest,
        "decision": decision,
        "reviewer_mode": "declared-human",
        "reviewer_id": reviewer_id,
        "checked_at": checked_at,
        "scope": scope,
    }
    value["receipt_digest"] = receipt_hash(value)
    return value


def check_receipt(value: object) -> dict:
    """Validate one exact declared-review receipt and its digest."""
    require(
        isinstance(value, dict) and set(value) == RECEIPT_KEYS,
        "Review receipt fields are invalid",
    )
    require(value["schema_version"] == SCHEMA_VERSION, "Schema version is invalid")
    require(valid_hash(value["candidate_digest"]), "Candidate digest is invalid")
    require(value["decision"] in DECISIONS, "Review decision is invalid")
    require(
        value["reviewer_mode"] == "declared-human",
        "Reviewer mode is invalid",
    )
    require(valid_reviewer(value["reviewer_id"]), "Reviewer ID is not opaque")
    require(valid_time(value["checked_at"]), "Review timestamp is invalid")
    check_scope(value["scope"])
    require(valid_hash(value["receipt_digest"]), "Receipt digest is invalid")
    require(
        value["receipt_digest"] == receipt_hash(value),
        "Receipt digest does not match its review",
    )
    return value
