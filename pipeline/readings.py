"""Validate reviewed readings against exact extracted source revisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ledger import load_readings
from lineage import provenance_for
from identity import same_route, source_format, valid_source
from pages import PageGapAuditIndex, load_page_audits
from paths import REVIEWED_READINGS_DIR
from privacy import validate_public
from quality import (
    INDEX_STATUSES,
    PAGE_GAP_AUDIT_QUALITY_FIELDS,
    TEXT_EXTRACTION_STATUSES,
    apply_page_audit,
    assess_text_quality,
    classify_text_quality,
    read_cached_text,
)
from rules import check, validate_competitor_panel, validate_schema
from scholar import cache_text, page_texts, verify_cache
from sources import select_sources


ROOT = Path(__file__).resolve().parents[1]
READINGS_DIR = REVIEWED_READINGS_DIR
READING_SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/reading.schema.json").read_text(encoding="utf-8"))
)


def validate_html_cache(entry: dict) -> None:
    """Recheck a present raw HTML artifact against its committed identity."""
    if source_format(entry) != "html":
        return
    text_relative = Path(entry["text_path"])
    html_path = ROOT / "data/cache/html" / f"{text_relative.stem}.html"
    if not html_path.exists():
        return
    payload = html_path.read_bytes()
    check(
        hashlib.sha256(payload).hexdigest() == entry["source_sha256"],
        f"HTML source cache drifted for {entry['stable_id']}",
    )
    verify_cache(payload, entry["stable_id"])
    check(
        len(page_texts(payload)) == entry["page_count"],
        f"HTML source page count drifted for {entry['stable_id']}",
    )
    check(
        hashlib.sha256(cache_text(payload).encode("utf-8")).hexdigest()
        == entry["text_sha256"],
        f"HTML extracted cache drifted for {entry['stable_id']}",
    )


def validate_reading(
    path: Path,
    reading: dict,
    maximum_page: int | None = None,
    source_entry: dict | None = None,
) -> None:
    """Validate the evidence-bearing parts of one structured reading."""
    validate_schema(READING_SCHEMA, reading, f"Reading {path.name}")
    validate_public(reading, f"Reading {path.name}")
    check(
        reading.get("reading_depth") in {"full_text", "verified"},
        f"Invalid depth in {path.name}",
    )
    check(reading.get("key_findings"), f"Missing findings in {path.name}")
    page_limit = maximum_page
    if page_limit is None and source_entry is not None:
        page_limit = source_entry.get("page_count")
    if page_limit is None:
        page_limit = reading["source_provenance"]["page_count"]
    for finding in reading["key_findings"]:
        anchors = finding.get("anchors", [])
        check(anchors, f"Unanchored finding in {path.name}")
        check(
            all(
                isinstance(anchor.get("page"), int) and anchor["page"] > 0
                for anchor in anchors
            ),
            f"Invalid page anchor in {path.name}",
        )
        if page_limit is not None:
            check(
                all(anchor["page"] <= page_limit for anchor in anchors),
                f"Page anchor exceeds the extracted source in {path.name}",
            )
    validate_competitor_panel(
        reading.get("competitive_landscape", []),
        minimum=3,
        label=f"Competitive landscape in {path.name}",
        excluded_id=reading["stable_id"],
    )
    novelty = reading.get("novelty_assessment")
    novelty_is_valid = bool(novelty) and (
        isinstance(novelty, str)
        or (
            isinstance(novelty, dict)
            and bool(novelty.get("author_claim"))
            and bool(novelty.get("reviewer_inference"))
        )
    )
    check(novelty_is_valid, f"Novelty assessment missing in {path.name}")
    check(
        isinstance(reading.get("confidence"), (int, float))
        and 0 <= reading["confidence"] <= 1,
        f"Reading confidence is invalid in {path.name}",
    )
    if source_entry is None:
        return
    missing_text_pages = set(source_entry.get("missing_text_pages", []))
    anchored_pages = {
        anchor["page"]
        for finding in reading["key_findings"]
        for anchor in finding["anchors"]
    }
    check(
        anchored_pages.isdisjoint(missing_text_pages),
        f"Finding cites a page without usable extracted text in {path.name}",
    )
    check(
        reading.get("source_provenance")
        == provenance_for(source_entry, reading["reading_depth"]),
        f"Reading source revision drifted in {path.name}",
    )


def validate_fulltext_integrity(
    entries: list[dict],
    gaps: PageGapAuditIndex | None = None,
) -> None:
    """Require usable-text metrics and verify cache bytes whenever they are present."""
    audits = gaps if gaps is not None else load_page_audits()
    stable_ids = [entry.get("stable_id") for entry in entries]
    check(
        all(isinstance(stable_id, str) and stable_id for stable_id in stable_ids)
        and len(stable_ids) == len(set(stable_ids)),
        "Full-text index contains a missing or duplicate stable ID",
    )
    metric_fields = (
        "text_sha256",
        "character_count",
        "useful_character_count",
        "pages_with_text",
        "missing_text_pages",
        "text_coverage_ratio",
        "useful_character_ratio",
    )
    for entry in entries:
        stable_id = entry["stable_id"]
        status = entry.get("status")
        check(status in INDEX_STATUSES, f"Unknown extraction status for {stable_id}")
        has_routed_source = (
            isinstance(entry.get("source_route"), str)
            and bool(entry["source_route"])
            and isinstance(entry.get("source_url") or entry.get("pdf_url"), str)
            and bool(entry.get("source_url") or entry.get("pdf_url"))
        )
        has_legacy_source = isinstance(entry.get("arxiv_id"), str) and bool(
            entry["arxiv_id"]
        )
        check(
            (has_routed_source or has_legacy_source)
            and isinstance(entry.get("processed_at"), str)
            and bool(entry["processed_at"]),
            f"Extraction source metadata is incomplete for {stable_id}",
        )
        if status == "extract_failed":
            check(
                not entry.get("text_path")
                and isinstance(entry.get("error_type"), str)
                and bool(entry["error_type"])
                and "error" not in entry,
                f"Extraction failure metadata is unsafe for {stable_id}",
            )
            continue
        check(
            status in TEXT_EXTRACTION_STATUSES
            and all(field in entry for field in metric_fields)
            and valid_source(entry)
            and isinstance(entry.get("text_sha256"), str)
            and len(entry["text_sha256"]) == 64
            and all(
                character in "0123456789abcdef" for character in entry["text_sha256"]
            ),
            f"Full-text integrity metrics are missing for {stable_id}",
        )
        missing_pages = entry["missing_text_pages"]
        check(
            isinstance(entry.get("page_count"), int)
            and entry["page_count"] > 0
            and isinstance(entry.get("character_count"), int)
            and entry["character_count"] >= 0
            and isinstance(entry.get("useful_character_count"), int)
            and 0 <= entry["useful_character_count"] <= entry["character_count"]
            and isinstance(entry.get("pages_with_text"), int)
            and 0 <= entry["pages_with_text"] <= entry["page_count"]
            and isinstance(missing_pages, list)
            and missing_pages == sorted(set(missing_pages))
            and all(
                isinstance(page, int) and 1 <= page <= entry["page_count"]
                for page in missing_pages
            )
            and entry["pages_with_text"] + len(missing_pages) == entry["page_count"]
            and isinstance(entry.get("text_coverage_ratio"), (int, float))
            and entry["text_coverage_ratio"]
            == round(entry["pages_with_text"] / entry["page_count"], 4)
            and isinstance(entry.get("useful_character_ratio"), (int, float))
            and 0 <= entry["useful_character_ratio"] <= 1,
            f"Full-text quality metrics are inconsistent for {stable_id}",
        )
        audit_fields = [field in entry for field in PAGE_GAP_AUDIT_QUALITY_FIELDS]
        check(
            not any(audit_fields) or all(audit_fields),
            f"Page-gap audit metadata is incomplete for {stable_id}",
        )
        check(
            not any(audit_fields) or source_format(entry) == "pdf",
            f"Page-gap audit requires a PDF source for {stable_id}",
        )
        if all(audit_fields):
            expected = apply_page_audit(
                entry,
                entry["page_count"],
                stable_id,
                entry["pdf_sha256"],
                audits,
            )
            check(
                expected["status"] == status
                and all(
                    expected.get(field) == entry[field]
                    for field in PAGE_GAP_AUDIT_QUALITY_FIELDS
                ),
                f"Page-gap audit metadata is inconsistent for {stable_id}",
            )
        else:
            check(
                status
                == classify_text_quality(
                    entry["useful_character_count"],
                    entry["page_count"],
                    entry["pages_with_text"],
                    entry["text_coverage_ratio"],
                    entry["useful_character_ratio"],
                ),
                f"Full-text quality metrics are inconsistent for {stable_id}",
            )
        attempted_pages = entry.get("ocr_attempted_pages")
        check(
            attempted_pages is None
            or (
                source_format(entry) == "pdf"
                and isinstance(attempted_pages, list)
                and attempted_pages == sorted(set(attempted_pages))
                and all(
                    isinstance(page, int) and 1 <= page <= entry["page_count"]
                    for page in attempted_pages
                )
            ),
            f"OCR attempt metadata is invalid for {stable_id}",
        )
        relative_path = Path(entry.get("text_path", ""))
        check(
            not relative_path.is_absolute()
            and ".." not in relative_path.parts
            and relative_path.parts[:3] == ("data", "cache", "text"),
            f"Full-text cache path is unsafe for {stable_id}",
        )
        validate_html_cache(entry)
        text_path = ROOT / relative_path
        if not text_path.exists():
            continue
        measured = assess_text_quality(read_cached_text(text_path), entry["page_count"])
        compared_fields = metric_fields
        if all(audit_fields) and source_format(entry) == "pdf":
            measured = apply_page_audit(
                measured,
                entry["page_count"],
                stable_id,
                entry["pdf_sha256"],
                audits,
            )
            compared_fields += PAGE_GAP_AUDIT_QUALITY_FIELDS
        check(
            entry.get("status") == measured["status"]
            and all(entry[field] == measured[field] for field in compared_fields),
            f"Full-text cache content drifted for {stable_id}",
        )


def validate_source_routes(entries: list[dict], records: list[dict]) -> None:
    """Reject indexed retrieval routes that drift from audited source records."""
    selected = select_sources(records)
    for entry in entries:
        stable_id = entry["stable_id"]
        pair = selected.get(stable_id)
        check(pair is not None, f"Extraction route is unresolved for {stable_id}")
        check(
            same_route(entry, pair[1]),
            f"Extraction route drifted for {stable_id}",
        )


def load_valid_readings(
    canonical_ids: set[str], fulltext_entries: list[dict], records: list[dict]
) -> dict[str, dict]:
    """Load each reading once and check its source and page-range provenance."""
    validate_fulltext_integrity(fulltext_entries)
    validate_source_routes(fulltext_entries, records)
    extracted_by_id = {
        entry["stable_id"]: entry
        for entry in fulltext_entries
        if entry.get("status") == "full_text_ok"
    }
    readings = load_readings(READINGS_DIR)
    reading_files = sorted(READINGS_DIR.glob("*.json"))
    check(
        {entry["stable_id"] for entry in fulltext_entries} <= canonical_ids,
        "Full-text index contains an orphaned canonical ID",
    )
    check(
        len(readings) == len(reading_files),
        "Duplicate stable IDs exist in reading files",
    )
    check(
        set(readings) <= canonical_ids,
        "A reading does not belong to the collection corpus",
    )
    check(
        set(readings) <= set(extracted_by_id),
        "A reading lacks successful full-text extraction provenance",
    )
    for path in reading_files:
        reading = json.loads(path.read_text())
        validate_reading(
            path,
            reading,
            maximum_page=extracted_by_id[reading["stable_id"]].get("page_count"),
            source_entry=extracted_by_id[reading["stable_id"]],
        )
    return readings
