"""Validate deterministic ledgers and their published byte-for-byte copies."""

from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path

from assets import paper_asset, validate_papers, validate_reading_assets
from arxiv import merge_record
from assign import build_reading_queue
from atlas import (
    COMPETITOR_PROVENANCE_PATH,
    FLAGSHIP_IDEAS_PATH,
    build_atlas_payload,
    paper_bundle,
    public_core,
    reconstruct_atlas,
)
from competitors import load_flagships
from ledger import build_coverage_snapshot, load_json_lines
from paths import REVIEWED_READINGS_DIR
from promote import base_records, build_corpus, load_days
from related import build_work_rows
from rules import check
from sources import build_source_inventory
from verify import build_verification_queue


ROOT = Path(__file__).resolve().parents[1]
READINGS_DIR = REVIEWED_READINGS_DIR
MAX_CORE_BYTES = 1024 * 1024
MAX_CORE_GZIP = 250 * 1024
MAX_PAPER_BYTES = 16 * 1024 * 1024
MAX_PAPER_GZIP = 4 * 1024 * 1024


def same_bytes(left: Path, right: Path) -> bool:
    """Compare generated artifacts without loading large files twice as JSON."""
    if not left.exists() or not right.exists():
        return False
    return (
        hashlib.sha256(left.read_bytes()).digest()
        == hashlib.sha256(right.read_bytes()).digest()
    )


def validate_data_budgets(core_path: Path, bundle_path: Path) -> None:
    """Fail when either static payload crosses its measured transfer budget."""
    core = core_path.read_bytes()
    bundle = bundle_path.read_bytes()
    check(len(core) <= MAX_CORE_BYTES, "Atlas core exceeds its decoded byte budget")
    check(
        len(gzip.compress(core, compresslevel=9)) <= MAX_CORE_GZIP,
        "Atlas core exceeds its gzip byte budget",
    )
    check(
        len(bundle) <= MAX_PAPER_BYTES,
        "Paper asset exceeds its decoded byte budget",
    )
    check(
        len(gzip.compress(bundle, compresslevel=9)) <= MAX_PAPER_GZIP,
        "Paper asset exceeds its gzip byte budget",
    )


def validate_progress(progress: dict, expected: dict) -> None:
    """Compare semantic ledger fields while allowing a refreshed timestamp."""
    for key, value in expected.items():
        if key != "updated_at":
            check(
                progress.get(key) == value, f"Coverage ledger is stale at field: {key}"
            )


def validate_corpus(manifest: dict, enriched: list[dict]) -> set[str]:
    """Validate base preservation and automatic daily corpus promotion."""
    source_path = ROOT / "data/source/papers.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    check(
        manifest["paper_count"] == len(source),
        "Public collection manifest count is stale",
    )
    check(
        manifest.get("sha256") == hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "Public collection manifest hash is stale",
    )
    check(
        manifest.get("upstream_entry_count")
        == len(source) + manifest.get("excluded_private_context", -1)
        and manifest.get("excluded_private_context") == 3,
        "Private context exclusion ledger is stale",
    )
    overrides = json.loads(
        (ROOT / "data/source/overrides.json").read_text(encoding="utf-8")
    )
    base = base_records(source, enriched)
    expected_base = [
        merge_record(paper, overrides.get(str(paper["id"]), {}), record)
        for paper, record in zip(source, base, strict=True)
    ]
    check(
        base == expected_base,
        "Enriched corpus is stale against current source or override decisions",
    )
    expected, report = build_corpus(expected_base, load_days())
    check(enriched == expected, "Enriched corpus is stale against daily promotion")
    stored_report = json.loads(
        (ROOT / "data/generated/promotion.json").read_text(encoding="utf-8")
    )
    check(stored_report == report, "Daily promotion report is stale")
    check(
        report["corpus_count"] == len(enriched) and report["base_count"] == len(source),
        "Daily promotion counts are inconsistent",
    )
    canonical_ids = {item["stable_id"] for item in enriched}
    base_ids = {item["stable_id"] for item in base}
    check(
        len(base_ids) == manifest["unique_canonical_records"],
        "Base canonical identifier count drifted",
    )
    check(
        sum(bool(item.get("abstract")) for item in enriched) >= 1990,
        "Abstract coverage regressed",
    )
    return canonical_ids


def validate_review_queues(
    generated: Path,
    enriched: list[dict],
    fulltext_entries: list[dict],
    readings: dict[str, dict],
) -> None:
    """Reject stale first-pass or independent-review assignment ledgers."""
    reading_queue = json.loads((generated / "reading_queue.json").read_text())
    verification_queue = json.loads((generated / "verification_queue.json").read_text())
    for label, queue in (
        ("Reading", reading_queue),
        ("Verification", verification_queue),
    ):
        check(
            isinstance(queue.get("batch_size"), int) and queue["batch_size"] > 0,
            f"{label} queue has an invalid batch size",
        )
    expected_reading = build_reading_queue(
        enriched,
        fulltext_entries,
        set(readings),
        batch_size=reading_queue["batch_size"],
    )
    expected_verification = build_verification_queue(
        enriched,
        readings,
        batch_size=verification_queue["batch_size"],
    )
    check(reading_queue == expected_reading, "Reading queue is stale")
    check(verification_queue == expected_verification, "Verification queue is stale")


def validate_coverage_artifacts(
    generated: Path,
    enriched: list[dict],
    fulltext_entries: list[dict],
    readings: dict[str, dict],
    progress: dict,
    atlas: dict,
) -> dict:
    """Recompute the authoritative coverage snapshot and reject stale copies."""
    source_inventory = build_source_inventory(enriched, fulltext_entries)
    source_summary = source_inventory["summary"]
    check(
        source_summary["paper_records"] + source_summary["non_paper_records"]
        == source_summary["canonical_records_classified"],
        "Paper and non-paper source classifications do not cover the corpus",
    )
    check(
        all(
            row["route"] == "non_paper" and not row["adapter_supported"]
            for row in source_inventory["records"]
            if not row["requires_reading"]
        ),
        "Non-paper context was incorrectly routed as a paper",
    )
    non_paper_ids = {
        row["stable_id"]
        for row in source_inventory["records"]
        if not row["requires_reading"]
    }
    check(
        set(readings).isdisjoint(non_paper_ids),
        "A contextual non-paper record received a fabricated paper reading",
    )
    expected = build_coverage_snapshot(
        enriched,
        fulltext_entries,
        readings,
        source_inventory,
    )
    validate_progress(progress, expected)
    check(
        atlas.get("coverage") == progress,
        "Atlas coverage is not the authoritative progress snapshot",
    )
    stored_inventory = json.loads((generated / "source_inventory.json").read_text())
    check(stored_inventory == source_inventory, "Full-text source inventory is stale")
    return expected


def validate_derived_payload(
    atlas: dict,
    enriched: list[dict],
    readings: dict[str, dict],
    fulltext_entries: list[dict],
    progress: dict,
) -> None:
    """Rebuild semantic sections in memory and reject same-count stale content."""
    flagships = load_flagships(FLAGSHIP_IDEAS_PATH, COMPETITOR_PROVENANCE_PATH)
    expected, _, _ = build_atlas_payload(
        enriched,
        readings,
        fulltext_entries,
        flagships,
        generated_at=atlas["meta"]["generated_at"],
        coverage_updated_at=progress["updated_at"],
    )
    for section in (
        "meta",
        "topics",
        "tricks",
        "papers",
        "repos",
        "ideas",
        "coverage",
    ):
        check(
            atlas.get(section) == expected[section],
            f"Atlas derived section is stale: {section}",
        )


def validate_related_work(
    generated: Path, enriched: list[dict], readings: dict[str, dict]
) -> None:
    """Keep lexical candidates distinct from externally reviewed competition."""
    related_rows = load_json_lines(generated / "related_work_candidates.jsonl")
    check(
        related_rows == build_work_rows(enriched, readings),
        "Related-work candidate queue is stale",
    )
    check(
        len(related_rows) == len(enriched),
        "Related-work queue does not cover every collection entry",
    )
    reviewed_rows = {
        row["stable_id"]
        for row in related_rows
        if row.get("review_status") == "reviewed"
    }
    check(reviewed_rows == set(readings), "Related-work review statuses are stale")
    check(
        all(
            len(row.get("reviewed_competitors", [])) >= 3
            and row["reviewed_competitors"]
            == readings[row["stable_id"]]["competitive_landscape"]
            for row in related_rows
            if row.get("review_status") == "reviewed"
        ),
        "Reviewed related-work evidence is missing or stale",
    )
    context_ids = {
        item["id"]
        for item in enriched
        if item.get("record_kind") == "non_paper_context"
    }
    not_applicable_ids = {
        row["collection_id"]
        for row in related_rows
        if row.get("review_status") == "not_applicable"
    }
    check(
        not_applicable_ids == context_ids,
        "Contextual entries were not excluded from paper related-work review",
    )


def validate_published_copies(
    atlas_path: Path,
    readings: dict[str, dict],
    *,
    include_dist: bool = True,
) -> None:
    """Require committed public data and production data to match."""
    public_path = ROOT / "web/public/data/atlas.json"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    bundle = paper_bundle(atlas)
    metadata, _ = paper_asset(bundle)
    expected_core = public_core(atlas, metadata)
    public_core_payload = json.loads(public_path.read_text(encoding="utf-8"))
    check(public_core_payload == expected_core, "Web public atlas core is stale")
    validate_papers(
        ROOT / "web/public/data/papers",
        public_core_payload["paper_asset"],
        bundle,
        ROOT / "web/public",
    )
    public_bundle_path = (
        ROOT / "web/public" / public_core_payload["paper_asset"]["path"].lstrip("/")
    )
    public_bundle = json.loads(public_bundle_path.read_text(encoding="utf-8"))
    validate_data_budgets(public_path, public_bundle_path)
    check(
        reconstruct_atlas(public_core_payload, public_bundle) == atlas,
        "Published split atlas does not reconstruct the canonical atlas",
    )
    validate_reading_assets(
        READINGS_DIR,
        ROOT / "web/public/data/readings",
        readings,
    )
    dist_path = ROOT / "web/dist/data/atlas.json"
    if not include_dist:
        return
    check(dist_path.exists(), "Built web atlas is missing; rebuild the UI")
    check(
        same_bytes(public_path, dist_path), "Built web atlas is stale; rebuild the UI"
    )
    dist_core = json.loads(dist_path.read_text(encoding="utf-8"))
    validate_papers(
        ROOT / "web/dist/data/papers",
        dist_core["paper_asset"],
        bundle,
        ROOT / "web/dist",
    )
    validate_reading_assets(
        READINGS_DIR,
        ROOT / "web/dist/data/readings",
        readings,
    )
