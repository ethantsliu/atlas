"""Immutable provenance contracts for synthesized research candidates."""

from __future__ import annotations

import hashlib
import json
import re

from privacy import unsafe_public


SCHEMA_VERSION = 1
KINDS = frozenset({"idea", "trick"})
REVIEW_STATUSES = frozenset({"unreviewed", "rejected"})
HASH_KEYS = frozenset({"source_id", "sha256"})
IDENTITY_KEYS = frozenset({"target", "intervention", "mechanism", "outcome"})
MANIFEST_KEYS = frozenset(
    {"schema_version", "generator_version", "corpus_digest", "source_hashes"}
)
CANDIDATE_KEYS = frozenset(
    {
        "schema_version",
        "generator_version",
        "corpus_digest",
        "kind",
        "identity",
        "support_ids",
        "source_hashes",
        "retrieval_sources",
        "retrieval_hash",
        "candidate_id",
        "candidate_digest",
        "review_status",
    }
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
ARXIV_ID = re.compile(r"^arxiv:(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})$")
IDENTITY_LIMITS = {
    "target": 160,
    "intervention": 200,
    "mechanism": 240,
    "outcome": 200,
}


def require(value: bool, message: str) -> None:
    """Raise one readable synthesis contract error."""
    if not value:
        raise ValueError(message)


def canonical_bytes(value: object) -> bytes:
    """Serialize a JSON value without platform- or insertion-order drift."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def hash_value(value: object) -> str:
    """Hash one canonical JSON value."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def valid_hash(value: object) -> bool:
    """Accept one lowercase SHA-256 value."""
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def valid_text(value: object) -> bool:
    """Accept canonical visible text without surrounding whitespace."""
    return isinstance(value, str) and bool(value) and value == value.strip()


def normalize_hashes(rows: object) -> list[dict[str, str]]:
    """Validate and sort unique content hashes by source identity."""
    require(isinstance(rows, list) and bool(rows), "Source hashes are empty")
    require(
        all(isinstance(row, dict) and set(row) == HASH_KEYS for row in rows),
        "Source hash fields are invalid",
    )
    require(
        all(valid_text(row["source_id"]) and valid_hash(row["sha256"]) for row in rows),
        "Source hash values are invalid",
    )
    ordered = sorted(rows, key=lambda row: row["source_id"])
    identifiers = [row["source_id"] for row in ordered]
    require(len(identifiers) == len(set(identifiers)), "Source hashes are duplicated")
    return [dict(row) for row in ordered]


def normalize_ids(values: object, kind: str) -> list[str]:
    """Validate sorted version-free arXiv support identities."""
    minimum = 2 if kind == "idea" else 1
    require(
        isinstance(values, list) and len(values) >= minimum,
        f"{kind.title()} support is incomplete",
    )
    require(
        all(isinstance(value, str) and ARXIV_ID.fullmatch(value) for value in values),
        "Support IDs are not canonical version-free arXiv IDs",
    )
    ordered = sorted(values)
    require(len(ordered) == len(set(ordered)), "Support IDs are duplicated")
    require(values == ordered, "Support IDs are not sorted")
    return ordered


def corpus_digest(rows: object) -> str:
    """Commit to the complete sorted source corpus."""
    return hash_value({"source_hashes": normalize_hashes(rows)})


def retrieval_hash(rows: object) -> str:
    """Commit to the exact sorted retrieval result set."""
    return hash_value({"retrieval": normalize_hashes(rows)})


def require_subset(rows: list[dict], manifest: dict, label: str) -> None:
    """Bind exact source identities and hashes to one corpus manifest."""
    available = {(row["source_id"], row["sha256"]) for row in manifest["source_hashes"]}
    requested = {(row["source_id"], row["sha256"]) for row in rows}
    require(requested <= available, f"{label} are not in the corpus manifest")


def check_version(value: object) -> None:
    """Require one compact reproducible generator version."""
    require(
        isinstance(value, str) and bool(VERSION.fullmatch(value)),
        "Generator version is invalid",
    )


def check_identity(value: object) -> None:
    """Require the stable semantic identity used across revisions."""
    require(
        isinstance(value, dict) and set(value) == IDENTITY_KEYS,
        "Candidate identity fields are invalid",
    )
    require(
        all(
            valid_text(value[field])
            and len(value[field]) <= IDENTITY_LIMITS[field]
            and not unsafe_public(value[field])
            for field in IDENTITY_KEYS
        ),
        "Candidate identity values are invalid",
    )


def candidate_id(kind: str, identity: dict) -> str:
    """Derive one corpus-independent concept identity."""
    require(kind in KINDS, "Candidate kind is invalid")
    check_identity(identity)
    digest = hash_value({"identity": identity, "kind": kind})
    return f"{kind}:{digest}"


def candidate_hash(value: dict) -> str:
    """Hash every immutable candidate field except its own digest."""
    body = {key: value[key] for key in CANDIDATE_KEYS - {"candidate_digest"}}
    return hash_value(body)


def make_manifest(generator_version: str, source_hashes: list[dict]) -> dict:
    """Build one compact corpus-generation provenance manifest."""
    check_version(generator_version)
    sources = normalize_hashes(source_hashes)
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": generator_version,
        "corpus_digest": corpus_digest(sources),
        "source_hashes": sources,
    }


def check_manifest(value: object) -> dict:
    """Validate an exact synthesis generation manifest."""
    require(
        isinstance(value, dict) and set(value) == MANIFEST_KEYS,
        "Synthesis manifest fields are invalid",
    )
    require(value["schema_version"] == SCHEMA_VERSION, "Schema version is invalid")
    check_version(value["generator_version"])
    sources = normalize_hashes(value["source_hashes"])
    require(sources == value["source_hashes"], "Source hashes are not sorted")
    require(
        value["corpus_digest"] == corpus_digest(sources),
        "Corpus digest is invalid",
    )
    return value


def make_candidate(
    manifest: dict,
    *,
    kind: str,
    identity: dict,
    support_ids: list[str],
    source_hashes: list[dict],
    retrieval: list[dict],
    review_status: str = "unreviewed",
) -> dict:
    """Build one content-verified synthesis candidate revision."""
    check_manifest(manifest)
    require(kind in KINDS, "Candidate kind is invalid")
    check_identity(identity)
    require(review_status in REVIEW_STATUSES, "Review status is invalid")
    supports = normalize_ids(support_ids, kind)
    sources = normalize_hashes(source_hashes)
    retrieved = normalize_hashes(retrieval)
    require_subset(sources, manifest, "Candidate sources")
    require_subset(retrieved, manifest, "Retrieval sources")
    value = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": manifest["generator_version"],
        "corpus_digest": manifest["corpus_digest"],
        "kind": kind,
        "identity": dict(identity),
        "support_ids": supports,
        "source_hashes": sources,
        "retrieval_sources": retrieved,
        "retrieval_hash": retrieval_hash(retrieved),
        "candidate_id": candidate_id(kind, identity),
        "review_status": review_status,
    }
    value["candidate_digest"] = candidate_hash(value)
    return value


def check_candidate(value: object, manifest: dict) -> dict:
    """Validate one candidate and bind it to its source generation."""
    check_manifest(manifest)
    require(
        isinstance(value, dict) and set(value) == CANDIDATE_KEYS,
        "Synthesis candidate fields are invalid",
    )
    require(value["schema_version"] == SCHEMA_VERSION, "Schema version is invalid")
    require(
        value["generator_version"] == manifest["generator_version"],
        "Candidate generator version is invalid",
    )
    require(
        value["corpus_digest"] == manifest["corpus_digest"],
        "Candidate corpus digest is invalid",
    )
    require(value["kind"] in KINDS, "Candidate kind is invalid")
    check_identity(value["identity"])
    supports = normalize_ids(value["support_ids"], value["kind"])
    require(supports == value["support_ids"], "Support IDs are not sorted")
    sources = normalize_hashes(value["source_hashes"])
    require(sources == value["source_hashes"], "Source hashes are not sorted")
    retrieved = normalize_hashes(value["retrieval_sources"])
    require(retrieved == value["retrieval_sources"], "Retrieval sources are not sorted")
    require_subset(sources, manifest, "Candidate sources")
    require_subset(retrieved, manifest, "Retrieval sources")
    require(
        value["retrieval_hash"] == retrieval_hash(retrieved),
        "Retrieval hash is invalid",
    )
    require(
        value["candidate_id"] == candidate_id(value["kind"], value["identity"]),
        "Candidate ID is invalid",
    )
    require(
        value["review_status"] in REVIEW_STATUSES,
        "Review status is invalid",
    )
    require(valid_hash(value["candidate_digest"]), "Candidate digest is invalid")
    require(
        value["candidate_digest"] == candidate_hash(value),
        "Candidate digest does not match its revision",
    )
    return value
