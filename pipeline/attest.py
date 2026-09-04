#!/usr/bin/env python3
"""Create declared-human attestations without publishing candidate ideas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from files import atomic_write_text
from packet import CHECKLIST_FIELDS, check_triage_packet
from review import DECISIONS, valid_reviewer, valid_time
from synth import hash_value, require


ROOT = Path(__file__).resolve().parents[1]
ATTEST_SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/attest.schema.json").read_text(encoding="utf-8"))
)
SCHEMA_VERSION = 1
STATUS = "declared-human-attestation"
NOTICE = (
    "Declared human review only; not authenticated proof, publication, "
    "or a novelty claim."
)
VERDICTS = frozenset({"pass", "hold", "reject"})
REVIEW_KEYS = frozenset({"reviewer_id", "checked_at", "decision", "checklist"})


def parse_args() -> argparse.Namespace:
    """Parse one local attestation build or validation request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def load_object(path: Path, label: str) -> dict:
    """Load one required JSON object without accepting container ambiguity."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} JSON is invalid") from error
    require(isinstance(value, dict), f"{label} must be one object")
    return value


def attest_digest(value: dict) -> str:
    """Hash every attestation field except its self-describing digest."""
    body = {key: item for key, item in value.items() if key != "attestation_digest"}
    return hash_value(body)


def validate_schema(value: object) -> None:
    """Raise the first strict attestation-schema error with its field path."""
    errors = sorted(
        ATTEST_SCHEMA.iter_errors(value), key=lambda error: list(error.absolute_path)
    )
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise ValueError(f"Attestation schema violation at {location}: {error.message}")


def check_review(value: object) -> dict:
    """Require explicit human verdicts and one consistent overall decision."""
    require(
        isinstance(value, dict) and set(value) == REVIEW_KEYS,
        "Attestation review fields are invalid",
    )
    require(valid_reviewer(value["reviewer_id"]), "Attestation reviewer is invalid")
    require(valid_time(value["checked_at"]), "Attestation timestamp is invalid")
    require(
        isinstance(value["decision"], str) and value["decision"] in DECISIONS,
        "Attestation decision is invalid",
    )
    checklist = value["checklist"]
    require(
        isinstance(checklist, dict) and set(checklist) == set(CHECKLIST_FIELDS),
        "Attestation checklist fields are invalid",
    )
    require(
        all(
            isinstance(verdict, str) and verdict in VERDICTS
            for verdict in checklist.values()
        ),
        "Attestation checklist verdicts must be explicit pass, hold, or reject",
    )
    verdicts = set(checklist.values())
    decision = value["decision"]
    consistent = (
        decision == "accept-provisional"
        and verdicts == {"pass"}
        or decision == "hold"
        and "hold" in verdicts
        and "reject" not in verdicts
        or decision == "reject"
        and "reject" in verdicts
    )
    require(consistent, "Attestation decision contradicts checklist verdicts")
    return value


def attest_value(packet: dict, review: dict) -> dict:
    """Project one checked packet and explicit review onto an attestation."""
    lineage = packet["lineage"]
    value = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "reviewer_mode": "declared-human",
        "reviewer_id": review["reviewer_id"],
        "checked_at": review["checked_at"],
        "decision": review["decision"],
        "packet_digest": packet["packet_digest"],
        "candidate_digest": lineage["candidate_digest"],
        "corpus_digest": lineage["corpus_digest"],
        "retrieval_digest": lineage["retrieval_digest"],
        "support_digest": lineage["support_digest"],
        "checklist": dict(review["checklist"]),
        "notice": NOTICE,
    }
    value["attestation_digest"] = attest_digest(value)
    return value


def make_attestation(
    packet: dict,
    candidate: dict,
    manifest: dict,
    retrieval: dict,
    support: dict,
    review: dict,
    *,
    archive_root: Path,
) -> dict:
    """Attest exactly one checked packet without creating a publishable idea."""
    check_triage_packet(
        packet,
        candidate,
        manifest,
        retrieval,
        support,
        archive_root=archive_root,
    )
    check_review(review)
    value = attest_value(packet, review)
    validate_schema(value)
    return value


def check_attestation(
    value: object,
    packet: dict,
    candidate: dict,
    manifest: dict,
    retrieval: dict,
    support: dict,
    *,
    archive_root: Path,
) -> dict:
    """Bind an attestation back to its one exact checked evidence packet."""
    validate_schema(value)
    check_triage_packet(
        packet,
        candidate,
        manifest,
        retrieval,
        support,
        archive_root=archive_root,
    )
    require(isinstance(value, dict), "Attestation must be an object")
    review = {
        "reviewer_id": value["reviewer_id"],
        "checked_at": value["checked_at"],
        "decision": value["decision"],
        "checklist": value["checklist"],
    }
    check_review(review)
    require(
        value["attestation_digest"] == attest_digest(value),
        "Attestation digest does not match its content",
    )
    require(
        value == attest_value(packet, review),
        "Attestation does not match its checked packet",
    )
    return value


def main() -> None:
    """Build or validate one local, non-publishing attestation artifact."""
    args = parse_args()
    packet = load_object(args.packet, "Packet")
    candidate = load_object(args.candidate, "Candidate")
    manifest = load_object(args.manifest, "Manifest")
    retrieval = load_object(args.retrieval, "Retrieval")
    support = load_object(args.support, "Support")
    if args.check:
        value = load_object(args.output, "Attestation")
        check_attestation(
            value,
            packet,
            candidate,
            manifest,
            retrieval,
            support,
            archive_root=args.archive,
        )
        print(f"Validated attestation {value['attestation_digest']}")
        return
    require(args.review is not None, "Attestation review JSON is required")
    review = load_object(args.review, "Review")
    value = make_attestation(
        packet,
        candidate,
        manifest,
        retrieval,
        support,
        review,
        archive_root=args.archive,
    )
    atomic_write_text(
        args.output,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"Built attestation {value['attestation_digest']}")


if __name__ == "__main__":
    main()
