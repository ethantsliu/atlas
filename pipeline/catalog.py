#!/usr/bin/env python3
"""Build a compact, provenance-bound catalog over the complete arXiv archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

from archive import MANIFEST_NAME, read_manifest, read_shard
from files import atomic_write_text
from ontology import TOPICS, TRICKS


VERSION = "catalog-1"
MIN_DIRECTION_SUPPORT = 10
MAX_DIRECTIONS = 2_000
MAX_SUPPORTS = 24
SCOPES = frozenset({"likely", "possible"})
SHA256 = "0123456789abcdef"


def parse_args() -> argparse.Namespace:
    """Parse one catalog build or validation request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--limit", type=int, default=MAX_DIRECTIONS)
    return parser.parse_args()


def file_hash(path: Path) -> str:
    """Hash one source artifact without retaining its bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def catalog_text(value: dict) -> str:
    """Serialize stable JSON without zero-padded scientific exponents."""
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return re.sub(r"e([+-])0+(\d+)", r"e\1\2", rendered)


def identifiers(rows: object, ontology: dict[str, list[str]]) -> set[str]:
    """Read one already-validated archive route list defensively."""
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Catalog routes are invalid")
    result = {row.get("id") for row in rows}
    if not all(isinstance(value, str) and value in ontology for value in result):
        raise ValueError("Catalog routes are invalid")
    return result


def author_signature(paper: dict) -> str:
    """Return a non-published stable signature for the first listed author."""
    authors = paper.get("authors")
    author = authors[0] if isinstance(authors, list) and authors else "unknown"
    value = unicodedata.normalize("NFKC", str(author)).casefold().strip()
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def keep_smallest(values: set[str], value: str, limit: int) -> None:
    """Retain a deterministic bounded sample independent of shard order."""
    values.add(value)
    if len(values) > limit:
        values.remove(max(values))


def direction_key(subject: str, technique: str) -> str:
    """Build one stable corpus-independent candidate identity."""
    body = f"{VERSION}\0{subject}\0{technique}".encode()
    return f"direction:{hashlib.sha256(body).hexdigest()[:16]}"


def association(joint: int, subject: int, technique: int, total: int) -> float:
    """Return normalized pointwise mutual information for exact paper counts."""
    if min(joint, subject, technique, total) <= 0:
        return 0.0
    probability = joint / total
    denominator = -math.log(probability)
    if denominator == 0:
        return 1.0
    value = math.log((joint * total) / (subject * technique)) / denominator
    return round(max(-1.0, min(1.0, value)), 6)


def update_direction(group: dict, paper: dict, manifest_hash: str) -> None:
    """Add one distinct paper to a bounded candidate-direction aggregate."""
    group["support_count"] += 1
    year = str(paper["published"])[:4]
    group["years"].add(year)
    keep_smallest(group["authors"], author_signature(paper), 3)
    canonical = f"arxiv:{paper['id']}"
    rank = hashlib.sha256(f"{manifest_hash}\0{canonical}".encode()).hexdigest()
    keep_smallest(group["supports"], f"{rank}\0{canonical}", MAX_SUPPORTS)


def chosen_supports(group: dict) -> list[str]:
    """Project the bounded min-hash reservoir into six stable public IDs."""
    return sorted(value.split("\0", 1)[1] for value in sorted(group["supports"])[:6])


def build_catalog(root: Path, limit: int = MAX_DIRECTIONS) -> dict:  # noqa: C901
    """Stream every promoted shard into compact exact aggregate counts."""
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 10_000
    ):
        raise ValueError("Catalog direction limit must be between 1 and 10000")
    index_path = root / MANIFEST_NAME
    manifest = read_manifest(root, verify_shards=False)
    shards = manifest.get("shards", [])
    if not index_path.is_file() or not shards:
        raise ValueError("Catalog requires a promoted corpus manifest")
    manifest_hash = file_hash(index_path)
    subjects: Counter[str] = Counter()
    primary_subjects: Counter[str] = Counter()
    areas_all: Counter[str] = Counter()
    areas_scope: Counter[str] = Counter()
    techniques_all: Counter[str] = Counter()
    techniques_scope: Counter[str] = Counter()
    eligible_subjects: Counter[str] = Counter()
    eligible_techniques: Counter[str] = Counter()
    directions: dict[tuple[str, str], dict] = {}
    scanned = 0
    eligible = 0
    months: list[str] = []
    for shard in sorted(shards, key=lambda row: row.get("month", "")):
        relative = shard.get("path")
        expected = shard.get("sha256")
        month = shard.get("month")
        if not all(
            isinstance(value, str) and value for value in (relative, expected, month)
        ):
            raise ValueError("Catalog shard metadata is invalid")
        path = root / relative
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Catalog shard is missing or drifted: {relative}")
        payload = read_shard(path)
        months.append(month)
        for paper in payload["papers"]:
            scanned += 1
            categories = set(paper["categories"])
            topics = identifiers(paper["topics"], TOPICS)
            tricks = identifiers(paper["tricks"], TRICKS)
            subjects.update(categories)
            primary_subjects.update({paper["primary_category"]})
            areas_all.update(topics)
            techniques_all.update(tricks)
            if paper["scope"] not in SCOPES:
                continue
            eligible += 1
            areas_scope.update(topics)
            techniques_scope.update(tricks)
            eligible_subjects.update(categories)
            eligible_techniques.update(tricks)
            for subject in categories:
                for technique in tricks:
                    group = directions.setdefault(
                        (subject, technique),
                        {
                            "support_count": 0,
                            "years": set(),
                            "authors": set(),
                            "supports": set(),
                        },
                    )
                    update_direction(group, paper, manifest_hash)
    source_count = manifest.get("counts", {}).get("all")
    if scanned != source_count or months != sorted(set(months)):
        raise ValueError("Catalog coverage does not match the promoted corpus")

    candidates = []
    for (subject, technique), group in directions.items():
        if (
            group["support_count"] < MIN_DIRECTION_SUPPORT
            or len(group["years"]) < 2
            or len(group["authors"]) < 3
        ):
            continue
        candidates.append(
            {
                "id": direction_key(subject, technique),
                "status": "candidate",
                "subject_id": subject,
                "technique_id": technique,
                "support_count": group["support_count"],
                "year_count": len(group["years"]),
                "independent_author_groups_at_least": 3,
                "npmi": association(
                    group["support_count"],
                    eligible_subjects[subject],
                    eligible_techniques[technique],
                    eligible,
                ),
                "support_ids": chosen_supports(group),
            }
        )
    candidates.sort(
        key=lambda row: (
            -row["support_count"],
            -row["npmi"],
            row["subject_id"],
            row["technique_id"],
        )
    )
    published = candidates[:limit]

    def family_rows(ontology: dict[str, list[str]], all_counts, scoped_counts):
        return [
            {
                "id": identifier,
                "label": identifier.replace("-", " "),
                "all_paper_count": all_counts[identifier],
                "in_scope_paper_count": scoped_counts[identifier],
            }
            for identifier in sorted(ontology)
        ]

    result = {
        "schema_version": 1,
        "generator_version": VERSION,
        "status": "corpus-derived",
        "corpus": {
            "manifest_sha256": manifest_hash,
            "source_count": source_count,
            "month_count": len(shards),
        },
        "coverage": {
            "scanned_papers": scanned,
            "eligible_direction_papers": eligible,
            "scanned_months": len(months),
        },
        "counts": {
            "broad_areas": len(TOPICS),
            "technique_families": len(TRICKS),
            "arxiv_subjects": len(subjects),
            "eligible_directions": len(candidates),
            "candidate_directions": len(published),
        },
        "areas": family_rows(TOPICS, areas_all, areas_scope),
        "techniques": family_rows(TRICKS, techniques_all, techniques_scope),
        "subjects": [
            {
                "id": identifier,
                "label": identifier,
                "paper_count": subjects[identifier],
                "primary_paper_count": primary_subjects[identifier],
            }
            for identifier in sorted(subjects)
        ],
        "directions": published,
        "notice": (
            "Candidate directions are corpus-derived subject-technique crossovers, "
            "not reviewed novelty or feasibility claims."
        ),
    }
    return check_catalog(result)


def check_catalog(value: object) -> dict:  # noqa: C901
    """Validate the compact public catalog without trusting its producer."""
    if not isinstance(value, dict):
        raise ValueError("Catalog root is invalid")
    required = {
        "schema_version",
        "generator_version",
        "status",
        "corpus",
        "coverage",
        "counts",
        "areas",
        "techniques",
        "subjects",
        "directions",
        "notice",
    }
    if set(value) != required or value.get("schema_version") != 1:
        raise ValueError("Catalog contract is invalid")
    corpus = value.get("corpus")
    coverage = value.get("coverage")
    counts = value.get("counts")
    if not all(isinstance(row, dict) for row in (corpus, coverage, counts)):
        raise ValueError("Catalog metadata is invalid")
    digest = corpus.get("manifest_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in SHA256 for c in digest)
    ):
        raise ValueError("Catalog corpus digest is invalid")
    integers = [
        corpus.get("source_count"),
        corpus.get("month_count"),
        coverage.get("scanned_papers"),
        coverage.get("eligible_direction_papers"),
        coverage.get("scanned_months"),
        *counts.values(),
    ]
    if not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in integers
    ):
        raise ValueError("Catalog counts are invalid")
    if (
        corpus["source_count"] != coverage["scanned_papers"]
        or corpus["month_count"] != coverage["scanned_months"]
        or counts.get("broad_areas") != len(TOPICS)
        or counts.get("technique_families") != len(TRICKS)
    ):
        raise ValueError("Catalog coverage counts disagree")
    areas = value.get("areas")
    techniques = value.get("techniques")
    subjects = value.get("subjects")
    directions = value.get("directions")
    if not all(
        isinstance(rows, list) for rows in (areas, techniques, subjects, directions)
    ):
        raise ValueError("Catalog collections are invalid")
    if [row.get("id") for row in areas] != sorted(TOPICS):
        raise ValueError("Catalog broad areas are invalid")
    if [row.get("id") for row in techniques] != sorted(TRICKS):
        raise ValueError("Catalog technique families are invalid")
    subject_ids = [row.get("id") for row in subjects]
    if subject_ids != sorted(set(subject_ids)) or counts.get("arxiv_subjects") != len(
        subjects
    ):
        raise ValueError("Catalog subjects are invalid")
    expected_directions = sorted(
        directions,
        key=lambda row: (
            -row.get("support_count", -1),
            -row.get("npmi", -2),
            row.get("subject_id", ""),
            row.get("technique_id", ""),
        ),
    )
    if (
        directions != expected_directions
        or counts.get("candidate_directions") != len(directions)
        or counts.get("eligible_directions", 0) < len(directions)
    ):
        raise ValueError("Catalog direction counts are invalid")
    for row in [*areas, *techniques]:
        if (
            not all(
                isinstance(row.get(key), int) and row[key] >= 0
                for key in ("all_paper_count", "in_scope_paper_count")
            )
            or row["in_scope_paper_count"] > row["all_paper_count"]
        ):
            raise ValueError("Catalog family counts are invalid")
    for row in directions:
        supports = row.get("support_ids")
        if (
            row.get("status") != "candidate"
            or row.get("subject_id") not in set(subject_ids)
            or row.get("technique_id") not in TRICKS
            or row.get("id") != direction_key(row["subject_id"], row["technique_id"])
            or not isinstance(row.get("support_count"), int)
            or row["support_count"] < MIN_DIRECTION_SUPPORT
            or not isinstance(row.get("year_count"), int)
            or row["year_count"] < 2
            or row.get("independent_author_groups_at_least") != 3
            or not isinstance(row.get("npmi"), (int, float))
            or not -1 <= row["npmi"] <= 1
            or not isinstance(supports, list)
            or not 1 <= len(supports) <= 6
            or supports != sorted(set(supports))
            or not all(
                isinstance(item, str) and item.startswith("arxiv:") for item in supports
            )
        ):
            raise ValueError("Catalog candidate direction is invalid")
    return value


def main() -> None:
    """Build or validate one catalog artifact."""
    args = parse_args()
    if args.check:
        value = json.loads(args.output.read_text(encoding="utf-8"))
        check_catalog(value)
        manifest = read_manifest(args.archive, verify_shards=False)
        if (
            value["corpus"]["manifest_sha256"]
            != file_hash(args.archive / MANIFEST_NAME)
            or value["corpus"]["source_count"] != manifest.get("counts", {}).get("all")
            or value["corpus"]["month_count"] != len(manifest.get("shards", []))
        ):
            raise ValueError("Catalog does not describe this promoted corpus")
        return
    value = build_catalog(args.archive, args.limit)
    atomic_write_text(args.output, catalog_text(value))


if __name__ == "__main__":
    main()
