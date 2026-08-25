#!/usr/bin/env python3
"""Build the compact graph, first-pass readings, and candidate research briefs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from ledger import (
    build_coverage_snapshot,
    load_json_lines,
    load_readings,
    write_coverage_snapshot,
)
from competitors import load_flagships
from paths import REVIEWED_READINGS_DIR
from ideas import (
    build_provisional_ideas,
)
from files import atomic_write_text
from ontology import TOPICS, TRICKS
from analysis import compact_paper
from sources import build_source_inventory, write_source_inventory
from assets import (
    prune_papers,
    prune_reading_assets,
    stage_papers,
    stage_reading_assets,
)

ROOT = Path(__file__).resolve().parents[1]
PAPERS_PATH = ROOT / "data/generated/papers_enriched.json"
OUTPUT_PATH = ROOT / "data/generated/atlas.json"
WEB_PATH = ROOT / "web/public/data/atlas.json"
WEB_PAPERS_DIR = ROOT / "web/public/data/papers"
WEB_ROOT = ROOT / "web/public"
LAYOUT_PATH = ROOT / "data/generated/layout.json"
FLAGSHIP_IDEAS_PATH = ROOT / "data/source/flagships.json"
COMPETITOR_PROVENANCE_PATH = ROOT / "data/source/competitors.json"
READINGS_DIR = REVIEWED_READINGS_DIR
WEB_READINGS_DIR = ROOT / "web/public/data/readings"
FULLTEXT_INDEX_PATH = ROOT / "data/generated/fulltext_index.jsonl"
PROGRESS_PATH = ROOT / "data/generated/progress.json"
SOURCE_INVENTORY_PATH = ROOT / "data/generated/source_inventory.json"
NOTICE = (
    "First-pass routing is keyword-backed. Read evidence level and confidence "
    "before treating a connection as a finding."
)
PAPER_LAYOUT_FIELDS = ("positions", "neighbors", "node_clusters")


def layout_split(payload: dict) -> tuple[dict | None, dict | None]:
    """Partition node-indexed layout maps at the paper boundary."""
    layout = payload.get("layout")
    if not isinstance(layout, dict):
        return None, None
    paper_ids = {paper["id"] for paper in payload["papers"]}
    core = deepcopy(layout)
    shard: dict = {}
    for field in PAPER_LAYOUT_FIELDS:
        values = layout.get(field)
        if not isinstance(values, dict):
            continue
        core[field] = {
            key: value for key, value in values.items() if key not in paper_ids
        }
        shard[field] = {key: value for key, value in values.items() if key in paper_ids}
    return core, shard


def paper_bundle(payload: dict) -> dict:
    """Project full paper metadata into its independently cached asset."""
    _, layout = layout_split(payload)
    if layout is None:
        raise RuntimeError("Atlas publication requires a semantic layout")
    bundle = {
        "schema_version": 1,
        "papers": payload["papers"],
        "layout": layout,
    }
    return bundle


def public_core(payload: dict, asset: dict) -> dict:
    """Project the map-first core and bind it to one immutable paper asset."""
    core = {key: value for key, value in payload.items() if key != "papers"}
    core_layout, _ = layout_split(payload)
    if core_layout is None:
        raise RuntimeError("Atlas publication requires a semantic layout")
    core["layout"] = core_layout
    return {
        "schema_version": 2,
        **core,
        "paper_asset": asset,
    }


def reconstruct_atlas(core: dict, bundle: dict) -> dict:
    """Rebuild the canonical atlas while enforcing split-map ownership."""
    atlas = {
        key: deepcopy(value)
        for key, value in core.items()
        if key not in {"schema_version", "paper_asset"}
    }
    papers = deepcopy(bundle.get("papers"))
    if not isinstance(papers, list):
        raise ValueError("Paper bundle lacks a paper list")
    atlas["papers"] = papers
    paper_ids = {paper.get("id") for paper in papers if isinstance(paper, dict)}
    core_ids = {
        *(f"topic:{item['id']}" for item in atlas.get("topics", [])),
        *(f"trick:{item['id']}" for item in atlas.get("tricks", [])),
        *(item["id"] for item in atlas.get("ideas", [])),
    }
    core_layout = atlas.get("layout")
    shard = bundle.get("layout")
    if not isinstance(core_layout, dict):
        if shard is not None:
            raise ValueError("Paper layout shard has no core layout")
        return atlas
    if shard is None:
        if any(
            paper_ids.intersection(core_layout.get(field, {}))
            for field in PAPER_LAYOUT_FIELDS
        ):
            raise ValueError("Paper layout shard is missing")
        return atlas
    if not isinstance(shard, dict):
        raise ValueError("Paper layout shard is invalid")
    for field in PAPER_LAYOUT_FIELDS:
        base = core_layout.get(field, {})
        extra = shard.get(field, {})
        if not isinstance(base, dict) or not isinstance(extra, dict):
            raise ValueError(f"Layout map is invalid: {field}")
        if set(base) != core_ids or set(extra) != paper_ids:
            raise ValueError(f"Layout map coverage is invalid: {field}")
        if set(base).intersection(extra):
            raise ValueError(f"Layout maps overlap: {field}")
        if paper_ids.intersection(base) or set(extra) - paper_ids:
            raise ValueError(f"Layout map ownership is invalid: {field}")
        core_layout[field] = {**base, **deepcopy(extra)}
    return atlas


def prior_path() -> str | None:
    """Read the paper asset used by the currently published core, if valid."""
    if not WEB_PATH.is_file():
        return None
    try:
        core = json.loads(WEB_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    asset = core.get("paper_asset") if isinstance(core, dict) else None
    path = asset.get("path") if isinstance(asset, dict) else None
    return path if isinstance(path, str) else None


def taxon_label(key: str) -> str:
    """Return the lowercase public vocabulary for a taxonomy key."""
    if key == "pre-training":
        return "pretraining"
    if key == "post-training":
        return "post-training"
    return key.replace("-", " ")


def build_ideas(
    papers: list[dict],
    flagships: list[dict],
) -> list[dict]:
    """Compose paper-grounded ideas without mutating source records."""
    ideas = build_provisional_ideas(papers)

    for source in flagships:
        flagship = deepcopy(source)
        flagship.pop("repo_names", None)
        flagship.pop("personal_relevance", None)
        flagship.pop("personal_paper_ids", None)
        flagship["repo_ids"] = []
        flagship["brief"]["repo_ids"] = []
        flagship["brief"].pop("personal_context", None)
        ideas.append(flagship)

    return sorted(
        ideas,
        key=lambda item: (
            -item["feasibility"]["score"],
            item["id"],
        ),
    )


def build_atlas_payload(
    raw_papers: list[dict],
    full_readings: dict[str, dict],
    fulltext_entries: list[dict],
    flagships: list[dict],
    *,
    generated_at: str,
    coverage_updated_at: str | None = None,
    layout: dict | None = None,
) -> tuple[dict, dict, dict]:
    """Purely derive the public payload, source inventory, and coverage ledger."""
    papers = [
        compact_paper(record, full_readings.get(record.get("stable_id")))
        for record in raw_papers
    ]
    research_papers = [
        paper for paper in papers if paper["record_kind"] != "non_paper_context"
    ]
    source_inventory = build_source_inventory(raw_papers, fulltext_entries)
    coverage = build_coverage_snapshot(
        raw_papers,
        fulltext_entries,
        full_readings,
        source_inventory,
        updated_at=coverage_updated_at or generated_at,
    )
    ideas = build_ideas(
        research_papers,
        flagships,
    )
    topic_counts = Counter(
        item["id"] for paper in research_papers for item in paper["topics"]
    )
    trick_counts = Counter(
        item["id"] for paper in research_papers for item in paper["tricks"]
    )
    payload = {
        "meta": {
            "generated_at": generated_at,
            "paper_count": len(papers),
            "research_entry_count": len(research_papers),
            "context_entry_count": len(papers) - len(research_papers),
            "repo_count": 0,
            "idea_count": len(ideas),
            "full_reading_count": coverage["full_readings"],
            "extracted_fulltext_count": coverage["fulltext_extracted"],
            "notice": NOTICE,
        },
        "topics": [
            {
                "id": key,
                "label": taxon_label(key),
                "paper_count": topic_counts[key],
            }
            for key in TOPICS
        ],
        "tricks": [
            {
                "id": key,
                "label": taxon_label(key),
                "paper_count": trick_counts[key],
            }
            for key in TRICKS
        ],
        "papers": papers,
        "repos": [],
        "ideas": ideas,
        "coverage": coverage,
    }
    if layout is not None:
        payload["layout"] = layout
    return payload, source_inventory, coverage


def publish_atlas_payload(payload: dict) -> None:
    """Publish details, paper asset, and core in an interruption-safe order."""
    previous_path = prior_path()
    staged_paths = stage_reading_assets(READINGS_DIR, WEB_READINGS_DIR)
    payload_paths = {
        paper["stable_id"]: paper["full_reading_path"]
        for paper in payload.get("papers", [])
        if paper.get("full_reading_path")
    }
    if payload_paths != staged_paths:
        raise RuntimeError(
            "Reviewed readings changed after the compact atlas payload was built"
        )
    bundle = paper_bundle(payload)
    paper_asset = stage_papers(WEB_PAPERS_DIR, bundle, WEB_ROOT)
    atomic_write_text(
        OUTPUT_PATH,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
    )
    atomic_write_text(
        WEB_PATH,
        json.dumps(
            public_core(payload, paper_asset),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
    )
    prune_reading_assets(READINGS_DIR, WEB_READINGS_DIR, staged_paths)
    prune_papers(WEB_PAPERS_DIR, paper_asset, previous_path, WEB_ROOT)


def write_base(payload: dict, inventory: dict, coverage: dict) -> None:
    """Write private layout inputs without publishing an incomplete web atlas."""
    if "layout" in payload:
        raise ValueError("Base atlas must not contain a semantic layout")
    write_source_inventory(SOURCE_INVENTORY_PATH, inventory)
    write_coverage_snapshot(PROGRESS_PATH, coverage)
    atomic_write_text(
        OUTPUT_PATH,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
    )


def main() -> None:
    """Load inputs, derive artifacts once, and publish them atomically."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        action="store_true",
        help="write private generated inputs without layout or web publication",
    )
    args = parser.parse_args()
    if not PAPERS_PATH.exists():
        raise SystemExit(
            "Missing data/generated/papers_enriched.json; run "
            "pipeline/arxiv.py before building the atlas."
        )
    raw_papers = json.loads(PAPERS_PATH.read_text(encoding="utf-8"))
    full_readings = load_readings(READINGS_DIR)
    fulltext_entries = load_json_lines(FULLTEXT_INDEX_PATH)
    flagships = load_flagships(FLAGSHIP_IDEAS_PATH, COMPETITOR_PROVENANCE_PATH)
    layout = (
        None
        if args.base
        else (
            json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
            if LAYOUT_PATH.exists()
            else None
        )
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    payload, source_inventory, coverage = build_atlas_payload(
        raw_papers,
        full_readings,
        fulltext_entries,
        flagships,
        generated_at=generated_at,
        layout=layout,
    )

    if args.base:
        write_base(payload, source_inventory, coverage)
    else:
        write_source_inventory(SOURCE_INVENTORY_PATH, source_inventory)
        write_coverage_snapshot(PROGRESS_PATH, coverage)
        publish_atlas_payload(payload)
    print(
        f"Built atlas: {payload['meta']['paper_count']} entries, "
        f"{payload['meta']['idea_count']} ideas"
    )


if __name__ == "__main__":
    main()
