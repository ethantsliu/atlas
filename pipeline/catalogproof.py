"""Integrity and source-lineage contracts for the public archive catalog."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from archive import read_manifest, read_shard
from ontology import TOPICS, TRICKS


VERSION = "catalog-2"
IDENTITY_VERSION = "catalog-1"
MIN_DIRECTION_SUPPORT = 10
MIN_DIRECTION_YEARS = 2
MIN_AUTHOR_GROUPS = 3
MAX_DIRECTIONS = 2_000
MAX_SUPPORTS = 24
PUBLISHED_SUPPORTS = 6
SCOPES = frozenset({"likely", "possible"})
SHA256 = "0123456789abcdef"
SUBJECT_ID = re.compile(r"^[A-Za-z][A-Za-z0-9.-]{1,31}$")
SUPPORT_ID = re.compile(r"^arxiv:\S+$")
SHARD_PATH = re.compile(r"^[0-9]{4}-[0-9]{2}(?:-[0-9a-f]{16})?\.json\.gz$")
CORPUS_KEYS = {"manifest_sha256", "source_count", "month_count"}
POLICY_KEYS = {
    "digest",
    "identity_version",
    "ontology_sha256",
    "scopes",
    "min_direction_support",
    "min_direction_years",
    "min_author_groups",
    "max_directions",
    "published_supports",
}
COVERAGE_KEYS = {
    "scanned_papers",
    "eligible_direction_papers",
    "scanned_months",
}
COUNT_KEYS = {
    "broad_areas",
    "technique_families",
    "arxiv_subjects",
    "eligible_directions",
    "candidate_directions",
}
FAMILY_KEYS = {"id", "label", "all_paper_count", "in_scope_paper_count"}
SUBJECT_KEYS = {"id", "label", "paper_count", "primary_paper_count"}
DIRECTION_KEYS = {
    "id",
    "status",
    "subject_id",
    "technique_id",
    "support_count",
    "year_count",
    "independent_author_groups_at_least",
    "npmi",
    "support_ids",
    "support_refs",
}
SUPPORT_KEYS = {"id", "month", "path", "sha256", "row"}


def canonical_hash(value: object) -> str:
    """Hash one JSON value without formatting or dictionary-order drift."""
    content = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def file_hash(path: Path) -> str:
    """Hash one supplied archive shard without retaining its bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def policy_contract(limit: int) -> dict:
    """Commit to the exact ontology and thresholds used for this catalog."""
    body = {
        "identity_version": IDENTITY_VERSION,
        "ontology_sha256": canonical_hash({"topics": TOPICS, "tricks": TRICKS}),
        "scopes": sorted(SCOPES),
        "min_direction_support": MIN_DIRECTION_SUPPORT,
        "min_direction_years": MIN_DIRECTION_YEARS,
        "min_author_groups": MIN_AUTHOR_GROUPS,
        "max_directions": limit,
        "published_supports": PUBLISHED_SUPPORTS,
    }
    return {"digest": canonical_hash(body), **body}


def catalog_hash(value: dict) -> str:
    """Commit to every catalog field except the digest itself."""
    return canonical_hash(
        {key: item for key, item in value.items() if key != "content_sha256"}
    )


def direction_key(subject: str, technique: str) -> str:
    """Build one stable corpus-independent candidate identity."""
    body = f"{IDENTITY_VERSION}\0{subject}\0{technique}".encode()
    return f"direction:{hashlib.sha256(body).hexdigest()}"


def whole(value: object) -> bool:
    """Return whether a public count is a non-negative integer, excluding bools."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_digest(value: object) -> bool:
    """Return whether one value is a lowercase SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and not any(character not in SHA256 for character in value)
    )


def check_metadata(value: dict) -> tuple[dict, dict, dict, dict]:
    """Validate catalog roots, provenance policy, and reconciled counts."""
    required = {
        "schema_version",
        "generator_version",
        "status",
        "content_sha256",
        "policy",
        "corpus",
        "coverage",
        "counts",
        "areas",
        "techniques",
        "subjects",
        "directions",
        "notice",
    }
    if (
        set(value) != required
        or value.get("schema_version") != 1
        or value.get("generator_version") != VERSION
        or value.get("status") != "corpus-derived"
        or not isinstance(value.get("notice"), str)
        or not value["notice"].strip()
    ):
        raise ValueError("Catalog contract is invalid")
    corpus = value.get("corpus")
    policy = value.get("policy")
    coverage = value.get("coverage")
    counts = value.get("counts")
    if (
        not all(isinstance(row, dict) for row in (corpus, policy, coverage, counts))
        or set(corpus) != CORPUS_KEYS
        or set(policy) != POLICY_KEYS
        or set(coverage) != COVERAGE_KEYS
        or set(counts) != COUNT_KEYS
    ):
        raise ValueError("Catalog metadata is invalid")
    maximum = policy.get("max_directions")
    if not whole(maximum) or not 1 <= maximum <= 10_000:
        raise ValueError("Catalog policy limit is invalid")
    if policy != policy_contract(maximum):
        raise ValueError("Catalog policy digest is invalid")
    if not valid_digest(corpus.get("manifest_sha256")):
        raise ValueError("Catalog corpus digest is invalid")
    integers = [
        corpus.get("source_count"),
        corpus.get("month_count"),
        coverage.get("scanned_papers"),
        coverage.get("eligible_direction_papers"),
        coverage.get("scanned_months"),
        *counts.values(),
    ]
    if not all(whole(item) for item in integers):
        raise ValueError("Catalog counts are invalid")
    if (
        corpus["source_count"] != coverage["scanned_papers"]
        or corpus["month_count"] != coverage["scanned_months"]
        or counts.get("broad_areas") != len(TOPICS)
        or counts.get("technique_families") != len(TRICKS)
        or coverage["eligible_direction_papers"] > corpus["source_count"]
        or counts["candidate_directions"] > counts["eligible_directions"]
        or counts["candidate_directions"] > policy["max_directions"]
    ):
        raise ValueError("Catalog coverage counts disagree")
    return corpus, policy, coverage, counts


def check_inventory(
    value: dict, corpus: dict, coverage: dict, counts: dict
) -> set[str]:
    """Validate public area, technique, and subject inventory rows."""
    areas = value.get("areas")
    techniques = value.get("techniques")
    subjects = value.get("subjects")
    directions = value.get("directions")
    if not all(
        isinstance(rows, list) for rows in (areas, techniques, subjects, directions)
    ) or not all(
        isinstance(row, dict)
        for rows in (areas, techniques, subjects, directions)
        for row in rows
    ):
        raise ValueError("Catalog collections are invalid")
    if [row.get("id") for row in areas] != sorted(TOPICS):
        raise ValueError("Catalog broad areas are invalid")
    if [row.get("id") for row in techniques] != sorted(TRICKS):
        raise ValueError("Catalog technique families are invalid")
    subject_ids = [row.get("id") for row in subjects]
    if (
        not all(isinstance(identifier, str) for identifier in subject_ids)
        or subject_ids != sorted(set(subject_ids))
        or counts.get("arxiv_subjects") != len(subjects)
    ):
        raise ValueError("Catalog subjects are invalid")
    for row in subjects:
        identifier = row.get("id")
        if (
            set(row) != SUBJECT_KEYS
            or not isinstance(identifier, str)
            or not SUBJECT_ID.fullmatch(identifier)
            or row.get("label") != identifier
            or not whole(row.get("paper_count"))
            or not whole(row.get("primary_paper_count"))
            or row["primary_paper_count"] > row["paper_count"]
            or row["paper_count"] > corpus["source_count"]
        ):
            raise ValueError("Catalog subject row is invalid")
    for row in [*areas, *techniques]:
        if (
            set(row) != FAMILY_KEYS
            or not isinstance(row.get("label"), str)
            or not row["label"]
            or not whole(row.get("all_paper_count"))
            or not whole(row.get("in_scope_paper_count"))
            or row["in_scope_paper_count"] > row["all_paper_count"]
            or row["all_paper_count"] > corpus["source_count"]
            or row["in_scope_paper_count"] > coverage["eligible_direction_papers"]
        ):
            raise ValueError("Catalog family counts are invalid")
    return set(subject_ids)


def valid_supports(row: dict) -> bool:
    """Validate compact support IDs and their exact promoted-shard references."""
    supports = row.get("support_ids")
    references = row.get("support_refs")
    if (
        not isinstance(supports, list)
        or not 1 <= len(supports) <= PUBLISHED_SUPPORTS
        or supports != sorted(set(supports))
        or not all(
            isinstance(item, str) and SUPPORT_ID.fullmatch(item) for item in supports
        )
        or not isinstance(references, list)
        or len(references) != len(supports)
    ):
        return False
    for support in references:
        if (
            not isinstance(support, dict)
            or set(support) != SUPPORT_KEYS
            or support.get("id") not in supports
            or not isinstance(support.get("month"), str)
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", support["month"])
            or not isinstance(support.get("path"), str)
            or not SHARD_PATH.fullmatch(support["path"])
            or not valid_digest(support.get("sha256"))
            or not whole(support.get("row"))
        ):
            return False
    return [support["id"] for support in references] == supports


def check_directions(
    value: dict, subjects: set[str], coverage: dict, counts: dict
) -> None:
    """Validate sorted, unique, explicitly provisional direction candidates."""
    directions = value["directions"]
    expected = sorted(
        directions,
        key=lambda row: (
            -row.get("support_count", -1),
            -row.get("npmi", -2),
            row.get("subject_id", ""),
            row.get("technique_id", ""),
        ),
    )
    identifiers = [row.get("id") for row in directions]
    pairs = [(row.get("subject_id"), row.get("technique_id")) for row in directions]
    if (
        not all(isinstance(identifier, str) for identifier in identifiers)
        or not all(
            isinstance(subject, str) and isinstance(trick, str)
            for subject, trick in pairs
        )
        or directions != expected
        or counts.get("candidate_directions") != len(directions)
        or counts.get("eligible_directions", 0) < len(directions)
        or len(set(identifiers)) != len(identifiers)
        or len(set(pairs)) != len(pairs)
    ):
        raise ValueError("Catalog direction counts are invalid")
    for row in directions:
        npmi = row.get("npmi")
        if (
            set(row) != DIRECTION_KEYS
            or row.get("status") != "candidate"
            or row.get("subject_id") not in subjects
            or row.get("technique_id") not in TRICKS
            or row.get("id") != direction_key(row["subject_id"], row["technique_id"])
            or not whole(row.get("support_count"))
            or row["support_count"] < MIN_DIRECTION_SUPPORT
            or row["support_count"] > coverage["eligible_direction_papers"]
            or not whole(row.get("year_count"))
            or row["year_count"] < MIN_DIRECTION_YEARS
            or row.get("independent_author_groups_at_least") != MIN_AUTHOR_GROUPS
            or not isinstance(npmi, (int, float))
            or isinstance(npmi, bool)
            or not math.isfinite(npmi)
            or not -1 <= npmi <= 1
            or not valid_supports(row)
        ):
            raise ValueError("Catalog candidate direction is invalid")


def check_catalog(value: object) -> dict:
    """Validate the compact public catalog without trusting its producer."""
    if not isinstance(value, dict):
        raise ValueError("Catalog root is invalid")
    corpus, _policy, coverage, counts = check_metadata(value)
    subjects = check_inventory(value, corpus, coverage, counts)
    check_directions(value, subjects, coverage, counts)
    if not valid_digest(value.get("content_sha256")) or value[
        "content_sha256"
    ] != catalog_hash(value):
        raise ValueError("Catalog content digest is invalid")
    return value


def route_ids(rows: object) -> set[str]:
    """Read validated technique routes needed for support resolution."""
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Catalog support routes are invalid")
    result = {row.get("id") for row in rows}
    if not all(isinstance(value, str) and value in TRICKS for value in result):
        raise ValueError("Catalog support routes are invalid")
    return result


def check_archive_supports(value: dict, root: Path) -> None:
    """Resolve every published support back to its exact promoted archive row."""
    manifest = read_manifest(root, verify_shards=False)
    source_rows = {row["path"]: row for row in manifest.get("shards", [])}
    requests: dict[str, list[tuple[dict, dict]]] = {}
    for direction in value["directions"]:
        for support in direction["support_refs"]:
            source = source_rows.get(support["path"])
            if (
                source is None
                or source.get("month") != support["month"]
                or source.get("sha256") != support["sha256"]
            ):
                raise ValueError("Catalog support source is not in the corpus")
            requests.setdefault(support["path"], []).append((direction, support))
    for relative, pairs in requests.items():
        path = root / relative
        if not path.is_file() or file_hash(path) != source_rows[relative]["sha256"]:
            raise ValueError("Catalog support shard is missing or drifted")
        papers = read_shard(path)["papers"]
        for direction, support in pairs:
            row = support["row"]
            if row >= len(papers):
                raise ValueError("Catalog support row is outside its shard")
            paper = papers[row]
            if (
                f"arxiv:{paper['id']}" != support["id"]
                or paper["scope"] not in SCOPES
                or direction["subject_id"] not in paper["categories"]
                or direction["technique_id"] not in route_ids(paper["tricks"])
            ):
                raise ValueError("Catalog support row does not support its direction")
