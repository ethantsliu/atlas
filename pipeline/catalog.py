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
from catalogproof import (
    MAX_DIRECTIONS,
    MAX_SUPPORTS,
    MIN_AUTHOR_GROUPS,
    MIN_DIRECTION_SUPPORT,
    MIN_DIRECTION_YEARS,
    PUBLISHED_SUPPORTS,
    SCOPES,
    VERSION,
    catalog_hash,
    check_archive_supports,
    check_catalog,
    direction_key,
    policy_contract,
)
from files import atomic_write_text
from ontology import TOPICS, TRICKS


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


def update_direction(
    group: dict,
    paper: dict,
    manifest_hash: str,
    shard: dict,
    row: int,
) -> None:
    """Add one distinct paper to a bounded candidate-direction aggregate."""
    group["support_count"] += 1
    year = str(paper["published"])[:4]
    group["years"].add(year)
    keep_smallest(group["authors"], author_signature(paper), MIN_AUTHOR_GROUPS)
    canonical = f"arxiv:{paper['id']}"
    rank = hashlib.sha256(f"{manifest_hash}\0{canonical}".encode()).hexdigest()
    group["supports"][rank] = {
        "id": canonical,
        "month": shard["month"],
        "path": shard["path"],
        "sha256": shard["sha256"],
        "row": row,
    }
    if len(group["supports"]) > MAX_SUPPORTS:
        del group["supports"][max(group["supports"])]


def chosen_supports(group: dict) -> list[dict]:
    """Project the bounded min-hash reservoir into exact archive references."""
    chosen = [
        group["supports"][rank]
        for rank in sorted(group["supports"])[:PUBLISHED_SUPPORTS]
    ]
    return sorted(chosen, key=lambda value: value["id"])


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
        for row, paper in enumerate(payload["papers"]):
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
                            "supports": {},
                        },
                    )
                    update_direction(group, paper, manifest_hash, shard, row)
    source_count = manifest.get("counts", {}).get("all")
    if scanned != source_count or months != sorted(set(months)):
        raise ValueError("Catalog coverage does not match the promoted corpus")

    candidates = []
    for (subject, technique), group in directions.items():
        if (
            group["support_count"] < MIN_DIRECTION_SUPPORT
            or len(group["years"]) < MIN_DIRECTION_YEARS
            or len(group["authors"]) < MIN_AUTHOR_GROUPS
        ):
            continue
        support_refs = chosen_supports(group)
        candidates.append(
            {
                "id": direction_key(subject, technique),
                "status": "candidate",
                "subject_id": subject,
                "technique_id": technique,
                "support_count": group["support_count"],
                "year_count": len(group["years"]),
                "independent_author_groups_at_least": MIN_AUTHOR_GROUPS,
                "npmi": association(
                    group["support_count"],
                    eligible_subjects[subject],
                    eligible_techniques[technique],
                    eligible,
                ),
                "support_ids": [support["id"] for support in support_refs],
                "support_refs": support_refs,
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
        "policy": policy_contract(limit),
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
    result["content_sha256"] = catalog_hash(result)
    return check_catalog(result)


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
        check_archive_supports(value, args.archive)
        return
    value = build_catalog(args.archive, args.limit)
    atomic_write_text(args.output, catalog_text(value))


if __name__ == "__main__":
    main()
