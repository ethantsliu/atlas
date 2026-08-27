#!/usr/bin/env python3
"""Fail loudly when artifacts overstate evidence or drift out of sync."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from artifacts import (
    validate_corpus,
    validate_coverage_artifacts,
    validate_derived_payload,
    validate_progress,
    validate_published_copies,
    validate_related_work,
    validate_review_queues,
)
from audit import CACHE_PATH as VECTOR_CACHE_PATH
from audit import audit_layout as audit_scientific_layout
from assets import is_public_path, reading_public_path
from briefs import (
    validate_brief_protocols,
    validate_experiment_plan,
    validate_feasibility,
    validate_idea_references,
    validate_portfolio_hierarchy,
    validate_researched_brief,
)
from feedcheck import validate_feed
from layoutcheck import validate_clusters, validate_layout
from ledger import load_json, load_json_lines, validate_json
from ontology import TOPICS, TRICKS
from privacy import validate_public, validate_strings
from titles import valid_title
from readings import (
    READINGS_DIR,
    load_valid_readings,
    validate_fulltext_integrity,
    validate_reading,
    validate_source_routes,
)
from rules import check, is_primary_url, validate_competitor_panel
from shapes import validate_idea_shape


ROOT = Path(__file__).resolve().parents[1]
__all__ = [
    "READINGS_DIR",
    "is_primary_url",
    "validate_atlas_contents",
    "validate_brief_protocols",
    "validate_clusters",
    "validate_competitor_panel",
    "validate_experiment_plan",
    "validate_feasibility",
    "validate_fulltext_integrity",
    "validate_idea_shape",
    "validate_layout",
    "validate_paper_routes",
    "validate_portfolio_hierarchy",
    "validate_progress",
    "validate_reading",
    "validate_source_routes",
    "validate_researched_brief",
    "validate_review_queues",
]


def validate_atlas_metadata(
    atlas: dict,
    enriched: list[dict],
    full_reading_ids: set[str],
    expected_progress: dict,
) -> list[dict]:
    """Validate top-level counts and return the paper-only corpus projection."""
    check(
        atlas["meta"]["paper_count"] == len(atlas["papers"]) == len(enriched),
        "Atlas paper count is inconsistent",
    )
    research_papers = [
        paper
        for paper in atlas["papers"]
        if paper.get("record_kind") != "non_paper_context"
    ]
    context_records = len(atlas["papers"]) - len(research_papers)
    check(context_records == 0, "Atlas must contain papers only")
    check(
        atlas["meta"].get("research_entry_count") == len(research_papers),
        "Atlas research-entry count is inconsistent",
    )
    check(
        atlas["meta"].get("context_entry_count") == context_records,
        "Atlas contextual-entry count is inconsistent",
    )
    check(
        all(
            not {"note", "section", "tags"}.intersection(paper)
            for paper in atlas["papers"]
        ),
        "Atlas papers contain curator-only fields",
    )
    paper_ids = [paper.get("stable_id") for paper in atlas["papers"]]
    check(
        all(paper_ids) and len(paper_ids) == len(set(paper_ids)),
        "Atlas papers contain duplicate stable records",
    )
    check(
        all(valid_title(paper.get("title")) for paper in atlas["papers"]),
        "Atlas papers contain unsafe titles",
    )
    check(
        atlas["meta"]["repo_count"] == 0 and atlas["repos"] == [],
        "Atlas must not publish repository records",
    )
    check(
        atlas["meta"]["idea_count"] == len(atlas["ideas"]),
        "Atlas idea count is inconsistent",
    )
    idea_ids = [idea.get("id") for idea in atlas["ideas"]]
    check(
        all(idea_ids) and len(idea_ids) == len(set(idea_ids)),
        "Atlas idea IDs are missing or duplicated",
    )
    check(
        atlas["meta"]["full_reading_count"] == len(full_reading_ids),
        "Atlas reading count is stale",
    )
    check(
        atlas["meta"]["extracted_fulltext_count"]
        == expected_progress["fulltext_extracted"],
        "Atlas full-text extraction count is stale",
    )
    atlas_reading_ids = {
        paper["stable_id"]
        for paper in atlas["papers"]
        if paper.get("full_reading_path")
    }
    check(atlas_reading_ids == full_reading_ids, "Atlas reading references are stale")
    return research_papers


def validate_paper_routes(
    atlas: dict,
    readings: dict[str, dict] | None = None,
) -> None:
    """Validate record kinds, taxonomy routes, and lazy-reading references."""
    for paper in atlas["papers"]:
        check(
            "full_reading" not in paper,
            f"Legacy embedded reading remains on {paper['id']}",
        )
        check(
            paper.get("record_kind") in {"paper", "non_paper_context"},
            f"Unknown collection record kind on {paper['id']}",
        )
        if paper["record_kind"] == "non_paper_context":
            check(
                paper["reading_depth"] == "context"
                and not paper.get("full_reading_path"),
                f"Contextual entry was presented as a paper reading: {paper['id']}",
            )
        else:
            check(
                paper.get("reading_depth")
                in {"metadata", "abstract", "full_text", "verified"},
                f"Unknown paper reading depth on {paper['id']}",
            )
        check(
            {item["id"] for item in paper["topics"]} <= set(TOPICS),
            f"Unknown topic route on {paper['id']}",
        )
        check(
            {item["id"] for item in paper["tricks"]} <= set(TRICKS),
            f"Unknown technique route on {paper['id']}",
        )
        has_depth = paper.get("reading_depth") in {"full_text", "verified"}
        has_path = bool(paper.get("full_reading_path"))
        check(
            has_depth == has_path,
            f"Reading depth and detail path disagree on {paper['id']}",
        )
        if not has_path:
            continue
        check(
            bool(paper.get("stable_id")) and is_public_path(paper["full_reading_path"]),
            f"Unsafe or stale detail path on {paper['id']}",
        )
        if readings is not None:
            reading = readings.get(paper["stable_id"])
            check(
                reading is not None
                and paper["full_reading_path"]
                == reading_public_path(paper["stable_id"], reading),
                f"Content address is stale on {paper['id']}",
            )


def validate_taxonomy_counts(atlas: dict, research_papers: list[dict]) -> None:
    """Require aggregate topic and technique counts to exclude context records."""
    validate_strings(atlas["topics"], "Public topics")
    validate_strings(atlas["tricks"], "Public tricks")
    expected_topic_counts = Counter(
        route["id"] for paper in research_papers for route in paper["topics"]
    )
    expected_trick_counts = Counter(
        route["id"] for paper in research_papers for route in paper["tricks"]
    )
    check(
        {item["id"]: item["paper_count"] for item in atlas["topics"]}
        == {key: expected_topic_counts[key] for key in TOPICS},
        "Topic distribution includes context or is otherwise stale",
    )
    check(
        {item["id"]: item["paper_count"] for item in atlas["tricks"]}
        == {key: expected_trick_counts[key] for key in TRICKS},
        "Technique distribution includes context or is otherwise stale",
    )


def validate_atlas_contents(
    atlas: dict,
    enriched: list[dict],
    readings: dict[str, dict],
    expected_progress: dict,
) -> None:
    """Validate graph foreign keys, evidence references, briefs, and scores."""
    full_reading_ids = set(readings)
    research_papers = validate_atlas_metadata(
        atlas,
        enriched,
        full_reading_ids,
        expected_progress,
    )
    validate_paper_routes(atlas, readings)
    validate_taxonomy_counts(atlas, research_papers)
    validate_layout(atlas, readings)
    validate_idea_references(atlas, set(), full_reading_ids)
    check(
        all(
            idea.get("repo_ids") == [] and idea.get("brief", {}).get("repo_ids") == []
            for idea in atlas["ideas"]
        ),
        "Atlas ideas must not publish repository references",
    )
    serialized = json.dumps(atlas, ensure_ascii=False).lower()
    check(
        re.search(r"/(?:users|home)/[^/]+/", serialized) is None,
        "Atlas contains a local device path",
    )
    check("personal_sources" not in atlas, "Atlas contains a personal source layer")
    check(
        all(
            "personal_relevance" not in idea
            and "personal_paper_ids" not in idea
            and "personal_context" not in idea.get("brief", {})
            for idea in atlas["ideas"]
        ),
        "Atlas ideas contain personal ranking or provenance fields",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-dist",
        action="store_true",
        help="Ignore the uncommitted web build during committed-artifact preflight",
    )
    args = parser.parse_args()
    generated = ROOT / "data/generated"
    validate_json(ROOT / "data/source", ROOT / "data/reviewed", generated)
    manifest = load_json(generated / "corpus_manifest.json")
    source = load_json(ROOT / "data/source/papers.json")
    enriched = load_json(generated / "papers_enriched.json")
    progress = load_json(generated / "progress.json")
    atlas_path = generated / "atlas.json"
    atlas = load_json(atlas_path)
    validate_public(source, "Public collection source")
    validate_public(enriched, "Enriched public collection")
    validate_public(atlas, "Atlas")
    fulltext_entries = load_json_lines(generated / "fulltext_index.jsonl")
    canonical_ids = validate_corpus(manifest, enriched)
    readings = load_valid_readings(canonical_ids, fulltext_entries, enriched)
    validate_review_queues(generated, enriched, fulltext_entries, readings)
    expected_progress = validate_coverage_artifacts(
        generated,
        enriched,
        fulltext_entries,
        readings,
        progress,
        atlas,
    )
    validate_atlas_contents(atlas, enriched, readings, expected_progress)
    if VECTOR_CACHE_PATH.exists():
        audit_scientific_layout(atlas, readings)
    validate_derived_payload(atlas, enriched, readings, fulltext_entries, progress)
    validate_related_work(generated, enriched, readings)
    validate_published_copies(
        atlas_path,
        readings,
        include_dist=not args.skip_dist,
    )
    validate_feed(include_dist=not args.skip_dist)
    print(
        json.dumps(
            {
                "collection_entries": len(enriched),
                "canonical_records": len(canonical_ids),
                "abstract_records": sum(
                    bool(item.get("abstract")) for item in enriched
                ),
                "fulltext_extracted": expected_progress["fulltext_extracted"],
                "full_readings": len(readings),
                "ideas": len(atlas["ideas"]),
                "artifacts_synchronized": True,
                "status": "valid",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
