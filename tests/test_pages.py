from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from quality import (  # noqa: E402
    MIN_REVIEWABLE_PAGE_COVERAGE,
    PAGE_GAP_AUDIT_QUALITY_FIELDS,
    apply_page_audit,
    assess_text_quality,
)
from pages import (  # noqa: E402
    PAGE_GAP_AUDIT_SCHEMA_VERSION,
    load_page_audits,
    match_page_audit,
    audit_sha256,
    validate_audit_data,
)
from validate import validate_fulltext_integrity  # noqa: E402


def valid_audit() -> dict:
    return {
        "stable_id": "arxiv:test",
        "pdf_sha256": "a" * 64,
        "page_count": 5,
        "missing_text_pages": [5],
        "pages": [
            {
                "page": 5,
                "classification": "blank",
                "evidence": "Rendered leaf is visually blank.",
            }
        ],
        "auditor": "Test visual reviewer",
        "audited_at": "2026-08-23",
        "evidence": "All extraction gaps were rendered and inspected.",
    }


def payload(*records: dict) -> dict:
    return {
        "schema_version": PAGE_GAP_AUDIT_SCHEMA_VERSION,
        "records": list(records),
    }


def partial_quality() -> dict:
    text = "".join(
        f"<<<PAGE {page}>>>\n"
        + (("A substantive research result 123. " * 20) if page < 5 else "")
        for page in range(1, 6)
    )
    return assess_text_quality(text, 5)


class PageGapAuditTests(unittest.TestCase):
    def test_audit_promotion(self) -> None:
        audit = valid_audit()
        audits = validate_audit_data(payload(audit))
        native = partial_quality()

        result = apply_page_audit(
            native,
            5,
            "arxiv:test",
            "a" * 64,
            audits,
        )

        self.assertLess(native["text_coverage_ratio"], MIN_REVIEWABLE_PAGE_COVERAGE)
        self.assertEqual(native["status"], "partial_text")
        self.assertEqual(result["status"], "full_text_ok")
        self.assertEqual(result["missing_text_pages"], [5])
        self.assertEqual(result["pages_with_text"], 4)
        self.assertEqual(result["text_coverage_ratio"], 0.8)
        self.assertEqual(result["audited_non_content_pages"], [5])
        self.assertEqual(result["audited_short_content_pages"], [])
        self.assertEqual(result["content_page_count"], 4)
        self.assertEqual(result["content_pages_with_text"], 4)
        self.assertEqual(result["content_text_coverage_ratio"], 1.0)
        self.assertEqual(result["page_gap_audit_sha256"], audit_sha256(audit))

    def test_short_content(self) -> None:
        audit = valid_audit()
        audit["pages"][0] = {
            "page": 5,
            "classification": "complete-short-text",
            "evidence": "The complete two-line bibliography continuation is extracted.",
        }
        audits = validate_audit_data(payload(audit))
        native = partial_quality()

        result = apply_page_audit(
            native,
            5,
            "arxiv:test",
            "a" * 64,
            audits,
        )

        self.assertEqual(result["status"], "full_text_ok")
        self.assertEqual(result["audited_non_content_pages"], [])
        self.assertEqual(result["audited_short_content_pages"], [5])
        self.assertEqual(result["content_page_count"], 5)
        self.assertEqual(result["content_pages_with_text"], 5)
        self.assertEqual(result["content_text_coverage_ratio"], 1.0)

    def test_audit_drift(self) -> None:
        audit = valid_audit()
        audits = validate_audit_data(payload(audit))
        native = partial_quality()

        for pdf_hash, missing_pages in (
            ("b" * 64, [5]),
            ("a" * 64, [4, 5]),
        ):
            with self.subTest(pdf_hash=pdf_hash, missing_pages=missing_pages):
                self.assertIsNone(
                    match_page_audit(
                        audits,
                        "arxiv:test",
                        pdf_hash,
                        5,
                        missing_pages,
                    )
                )
        invalidated = apply_page_audit(
            {**native, "page_gap_audit_sha256": "stale"},
            5,
            "arxiv:test",
            "b" * 64,
            audits,
        )
        self.assertEqual(invalidated["status"], "partial_text")
        self.assertTrue(
            all(field not in invalidated for field in PAGE_GAP_AUDIT_QUALITY_FIELDS)
        )

    def test_hash_drift(self) -> None:
        audits = validate_audit_data(payload(valid_audit()))
        quality = apply_page_audit(
            partial_quality(),
            5,
            "arxiv:test",
            "a" * 64,
            audits,
        )
        entry = {
            "stable_id": "arxiv:test",
            "source_route": "arxiv",
            "pdf_url": "https://arxiv.org/pdf/test",
            "pdf_sha256": "a" * 64,
            "page_count": 5,
            "text_path": "data/cache/text/nonexistent-page-gap-test.txt",
            "processed_at": "2026-08-23T00:00:00+00:00",
            **quality,
        }
        validate_fulltext_integrity([entry], audits)

        entry["pdf_sha256"] = "b" * 64
        with self.assertRaisesRegex(RuntimeError, "audit metadata is inconsistent"):
            validate_fulltext_integrity([entry], audits)

    def test_review_contract(self) -> None:
        cases = []
        wrong_page = valid_audit()
        wrong_page["pages"][0]["page"] = 4
        cases.append(wrong_page)
        invalid_class = valid_audit()
        invalid_class["pages"][0]["classification"] = "probably-blank"
        cases.append(invalid_class)
        blank_evidence = valid_audit()
        blank_evidence["pages"][0]["evidence"] = " "
        cases.append(blank_evidence)
        unsorted = valid_audit()
        unsorted["missing_text_pages"] = [5, 4]
        unsorted["pages"].append(
            {"page": 4, "classification": "blank", "evidence": "Blank."}
        )
        cases.append(unsorted)

        for record in cases:
            with self.subTest(record=record):
                with self.assertRaises(RuntimeError):
                    validate_audit_data(payload(record))

    def test_audit_fields(self) -> None:
        audit = valid_audit()
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            validate_audit_data(payload(audit, copy.deepcopy(audit)))

        audit["approval"] = True
        with self.assertRaisesRegex(RuntimeError, "unexpected fields"):
            validate_audit_data(payload(audit))

    def test_source_audit(self) -> None:
        source_path = Path(__file__).resolve().parents[1] / "data/source/gaps.json"
        audits = load_page_audits(source_path)
        record = match_page_audit(
            audits,
            "arxiv:2406.11014",
            "2fea2bdb2725925666e2d9ea9f97dd42ed1cda4a6d5bfa9f08f548c35097b81a",
            134,
            [
                4,
                6,
                10,
                12,
                14,
                23,
                24,
                27,
                28,
                37,
                38,
                44,
                64,
                66,
                68,
                80,
                81,
                82,
                88,
                89,
                90,
                92,
                98,
                99,
                100,
            ],
        )
        self.assertIsNotNone(record)
        self.assertEqual(len(record["pages"]), 25)

    def test_json_utf8(self) -> None:
        source_path = Path(__file__).resolve().parents[1] / "data/source/gaps.json"
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "audits.json"
            copied.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(
                json.loads(copied.read_text(encoding="utf-8"))["schema_version"],
                PAGE_GAP_AUDIT_SCHEMA_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
