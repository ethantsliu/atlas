"""Validate hash-pinned visual audits of non-content PDF page gaps.

Native extraction metrics remain authoritative.  An audit is only eligible when
its stable ID, PDF hash, page count, and complete missing-page set all match the
current extraction.  This module deliberately does not classify pages itself;
it only validates and matches explicit visual-review records.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rules import check, is_filled, is_iso_date, is_sha256

ROOT = Path(__file__).resolve().parents[1]
PAGE_GAP_AUDITS = ROOT / "data/source/gaps.json"
PAGE_GAP_AUDIT_SCHEMA_VERSION = "page-gap-audits-v1"
NON_CONTENT_CLASSIFICATIONS = {"blank", "divider", "non-content"}
SHORT_CONTENT_CLASSIFICATIONS = {"complete-short-text"}
PAGE_CLASSIFICATIONS = NON_CONTENT_CLASSIFICATIONS | SHORT_CONTENT_CLASSIFICATIONS
AUDIT_FIELDS = {
    "stable_id",
    "pdf_sha256",
    "page_count",
    "missing_text_pages",
    "pages",
    "auditor",
    "audited_at",
    "evidence",
}
PAGE_FIELDS = {"page", "classification", "evidence"}

PageGapAuditIndex = dict[tuple[str, str], dict]


def validate_page_audit(record: object) -> dict:
    """Validate one exact-revision audit and return it with a narrow type."""
    check(isinstance(record, dict), "Page-gap audit record is not an object")
    unknown_fields = set(record) - AUDIT_FIELDS
    missing_fields = AUDIT_FIELDS - set(record)
    check(
        not unknown_fields and not missing_fields,
        "Page-gap audit record has unexpected fields: "
        f"missing={sorted(missing_fields)}, unknown={sorted(unknown_fields)}",
    )
    stable_id = record["stable_id"]
    check(is_filled(stable_id), "Page-gap audit has an invalid stable ID")
    label = f"Page-gap audit {stable_id}"
    check(is_sha256(record["pdf_sha256"]), f"{label} has an invalid PDF hash")
    page_count = record["page_count"]
    check(
        isinstance(page_count, int)
        and not isinstance(page_count, bool)
        and page_count > 1,
        f"{label} has an invalid page count",
    )
    missing_pages = record["missing_text_pages"]
    check(
        isinstance(missing_pages, list)
        and missing_pages
        and missing_pages == sorted(set(missing_pages))
        and all(
            isinstance(page, int)
            and not isinstance(page, bool)
            and 1 <= page <= page_count
            for page in missing_pages
        )
        and len(missing_pages) < page_count,
        f"{label} has an invalid missing-page set",
    )
    pages = record["pages"]
    check(
        isinstance(pages, list) and len(pages) == len(missing_pages),
        f"{label} needs one page review per missing page",
    )
    reviewed_page_numbers = []
    for page_review in pages:
        check(isinstance(page_review, dict), f"{label} has a non-object page review")
        check(
            set(page_review) == PAGE_FIELDS,
            f"{label} has an unexpected page-review shape",
        )
        page_number = page_review["page"]
        reviewed_page_numbers.append(page_number)
        check(
            page_review["classification"] in PAGE_CLASSIFICATIONS,
            f"{label} page {page_number} has an invalid classification",
        )
        check(
            is_filled(page_review["evidence"]),
            f"{label} page {page_number} lacks visual evidence",
        )
    check(
        reviewed_page_numbers == missing_pages,
        f"{label} page reviews do not exactly match the missing-page set",
    )
    check(is_filled(record["auditor"]), f"{label} has no auditor")
    check(is_iso_date(record["audited_at"]), f"{label} has an invalid audit date")
    check(is_filled(record["evidence"]), f"{label} has no audit evidence")
    return record


def validate_audit_data(payload: object) -> PageGapAuditIndex:
    """Validate the source envelope and index records by stable ID plus PDF hash."""
    check(isinstance(payload, dict), "Page-gap audit payload is not an object")
    check(
        set(payload) == {"schema_version", "records"},
        "Page-gap audit payload has an unexpected shape",
    )
    check(
        payload["schema_version"] == PAGE_GAP_AUDIT_SCHEMA_VERSION,
        "Page-gap audit schema version is unsupported",
    )
    records = payload["records"]
    check(isinstance(records, list), "Page-gap audit records are not a list")
    indexed: PageGapAuditIndex = {}
    for raw_record in records:
        record = validate_page_audit(raw_record)
        key = (record["stable_id"], record["pdf_sha256"])
        check(key not in indexed, f"Duplicate page-gap audit revision: {key[0]}")
        indexed[key] = record
    return indexed


def load_page_audits(path: Path = PAGE_GAP_AUDITS) -> PageGapAuditIndex:
    """Load the required, versioned source-side audit contract."""
    if not path.is_file():
        raise RuntimeError(f"Missing page-gap audit source: {path}")
    return validate_audit_data(json.loads(path.read_text(encoding="utf-8")))


def match_page_audit(
    audits: PageGapAuditIndex,
    stable_id: str,
    pdf_sha256: str,
    page_count: int,
    missing_text_pages: list[int],
) -> dict | None:
    """Return an audit only for an exact PDF revision and extraction page set."""
    audit = audits.get((stable_id, pdf_sha256))
    if not audit:
        return None
    if (
        audit["page_count"] != page_count
        or audit["missing_text_pages"] != missing_text_pages
    ):
        return None
    return audit


def audit_sha256(audit: dict) -> str:
    """Content-address an audit so derived quality metadata is traceable."""
    canonical = json.dumps(
        audit,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
