"""Classify extracted text and apply exact-revision page-gap audits."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pages import (
    NON_CONTENT_CLASSIFICATIONS,
    SHORT_CONTENT_CLASSIFICATIONS,
    PageGapAuditIndex,
    audit_sha256,
    match_page_audit,
)


PAGE_MARKER = re.compile(r"<<<PAGE \d+>>>")
MIN_USEFUL_PAGE_CHARACTERS = 40
MIN_REVIEWABLE_PAGE_COVERAGE = 0.85
TEXT_EXTRACTION_STATUSES = {
    "full_text_ok",
    "partial_text",
    "low_quality",
    "needs_ocr",
}
INDEX_STATUSES = {*TEXT_EXTRACTION_STATUSES, "extract_failed"}
PAGE_GAP_AUDIT_QUALITY_FIELDS = (
    "audited_non_content_pages",
    "audited_short_content_pages",
    "content_page_count",
    "content_pages_with_text",
    "content_text_coverage_ratio",
    "page_gap_audit_sha256",
)


def read_cached_text(path: Path) -> str:
    """Decode cached UTF-8 without universal-newline rewriting."""
    return path.read_bytes().decode("utf-8", errors="replace")


def classify_text_quality(
    useful_character_count: int,
    page_count: int,
    pages_with_text: int,
    text_coverage_ratio: float,
    useful_character_ratio: float,
) -> str:
    """Classify metrics with one reusable extraction policy."""
    if useful_character_count < 500 or pages_with_text == 0:
        return "needs_ocr"
    if (
        useful_character_count < max(1_000, page_count * 100)
        or text_coverage_ratio < 0.5
        or useful_character_ratio < 0.35
    ):
        return "low_quality"
    if text_coverage_ratio < MIN_REVIEWABLE_PAGE_COVERAGE:
        return "partial_text"
    return "full_text_ok"


def assess_text_quality(text: str, page_count: int) -> dict:
    """Measure extract usability without counting page markers as prose."""
    page_bodies = PAGE_MARKER.split(text)[1:]
    body_text = "".join(page_bodies)
    useful_character_count = sum(character.isalnum() for character in body_text)
    non_whitespace_count = sum(not character.isspace() for character in body_text)
    missing_text_pages = [
        page_number
        for page_number, body in enumerate(page_bodies, start=1)
        if sum(character.isalnum() for character in body) < MIN_USEFUL_PAGE_CHARACTERS
    ]
    pages_with_text = len(page_bodies) - len(missing_text_pages)
    text_coverage_ratio = round(pages_with_text / max(1, page_count), 4)
    useful_character_ratio = round(
        useful_character_count / max(1, non_whitespace_count), 4
    )
    status = classify_text_quality(
        useful_character_count,
        page_count,
        pages_with_text,
        text_coverage_ratio,
        useful_character_ratio,
    )
    return {
        "status": status,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "character_count": len(text),
        "useful_character_count": useful_character_count,
        "pages_with_text": pages_with_text,
        "missing_text_pages": missing_text_pages,
        "text_coverage_ratio": text_coverage_ratio,
        "useful_character_ratio": useful_character_ratio,
    }


def apply_page_audit(
    quality: dict,
    page_count: int,
    stable_id: str,
    pdf_sha256: str,
    audits: PageGapAuditIndex,
) -> dict:
    """Reclassify content coverage only when an exact visual audit matches."""
    result = {
        key: value
        for key, value in quality.items()
        if key not in PAGE_GAP_AUDIT_QUALITY_FIELDS
    }
    result["status"] = classify_text_quality(
        result["useful_character_count"],
        page_count,
        result["pages_with_text"],
        result["text_coverage_ratio"],
        result["useful_character_ratio"],
    )
    audit = match_page_audit(
        audits,
        stable_id,
        pdf_sha256,
        page_count,
        result["missing_text_pages"],
    )
    if not audit:
        return result

    non_content_pages = [
        review["page"]
        for review in audit["pages"]
        if review["classification"] in NON_CONTENT_CLASSIFICATIONS
    ]
    short_content_pages = [
        review["page"]
        for review in audit["pages"]
        if review["classification"] in SHORT_CONTENT_CLASSIFICATIONS
    ]
    content_page_count = page_count - len(non_content_pages)
    content_pages_with_text = result["pages_with_text"] + len(short_content_pages)
    content_text_coverage_ratio = round(
        content_pages_with_text / content_page_count,
        4,
    )
    result.update(
        {
            "status": classify_text_quality(
                result["useful_character_count"],
                content_page_count,
                content_pages_with_text,
                content_text_coverage_ratio,
                result["useful_character_ratio"],
            ),
            "audited_non_content_pages": non_content_pages,
            "audited_short_content_pages": short_content_pages,
            "content_page_count": content_page_count,
            "content_pages_with_text": content_pages_with_text,
            "content_text_coverage_ratio": content_text_coverage_ratio,
            "page_gap_audit_sha256": audit_sha256(audit),
        }
    )
    return result
