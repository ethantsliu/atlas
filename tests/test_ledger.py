from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from ledger import (  # noqa: E402
    build_coverage_snapshot,
    load_json,
    load_json_lines,
    public_extraction_issue,
    validate_json,
)


class CoverageTests(unittest.TestCase):
    def test_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            reviewed = root / "reviewed"
            generated = root / "generated"
            for path in (source, reviewed, generated):
                path.mkdir()
            duplicate = source / "papers.json"
            duplicate.write_text('{"id": 1, "id": 2}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Duplicate JSON object key"):
                load_json(duplicate)
            with self.assertRaisesRegex(RuntimeError, "Duplicate JSON object key"):
                validate_json(source, reviewed, generated)

            duplicate.unlink()
            lines = generated / "records.jsonl"
            lines.write_text('{"id": 1}\n{"id": 2, "id": 3}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, r"records\.jsonl:2"):
                load_json_lines(lines)

    def test_duplicate_entries(self) -> None:
        papers = [
            {"stable_id": "arxiv:1", "abstract": "a"},
            {"stable_id": "arxiv:1", "abstract": "a"},
            {"stable_id": "arxiv:2"},
        ]
        index = [{"stable_id": "arxiv:1", "status": "full_text_ok"}]
        readings = {
            "arxiv:1": {
                "stable_id": "arxiv:1",
                "competitive_landscape": [{"title": "prior"}],
            }
        }
        inventory = {
            "summary": {
                "canonical_records_classified": 2,
                "adapter_supported": 1,
                "adapter_missing": 1,
                "by_route": {"arxiv": 1, "manual_review": 1},
                "by_extraction_status": {"adapter_missing": 1, "full_text_ok": 1},
            },
            "records": [
                {"stable_id": "arxiv:1", "adapter_supported": True},
                {"stable_id": "arxiv:2", "adapter_supported": False},
            ],
        }
        snapshot = build_coverage_snapshot(papers, index, readings, inventory)
        self.assertEqual(snapshot["collection_entries"], 3)
        self.assertEqual(snapshot["canonical_records"], 2)
        self.assertEqual(snapshot["fulltext_extracted"], 1)
        self.assertEqual(snapshot["full_readings"], 1)
        self.assertEqual(snapshot["entry_reading_depth"]["full_text"], 2)
        self.assertEqual(snapshot["source_access"]["adapter_missing"], 1)

    def test_context_gate(self) -> None:
        papers = [
            {"stable_id": "arxiv:1", "abstract": "a"},
            {
                "stable_id": "urlhash:context",
                "record_kind": "non_paper_context",
            },
        ]
        readings = {
            "arxiv:1": {
                "stable_id": "arxiv:1",
                "competitive_landscape": [{"title": "prior"}],
            }
        }
        inventory = {
            "summary": {
                "canonical_records_classified": 2,
                "paper_records": 1,
                "non_paper_records": 1,
                "adapter_supported": 1,
                "adapter_missing": 0,
                "by_route": {"arxiv": 1, "non_paper": 1},
                "by_extraction_status": {"pending": 1, "not_applicable": 1},
            },
            "records": [
                {
                    "stable_id": "arxiv:1",
                    "adapter_supported": True,
                    "requires_reading": True,
                },
                {
                    "stable_id": "urlhash:context",
                    "adapter_supported": False,
                    "requires_reading": False,
                },
            ],
        }
        snapshot = build_coverage_snapshot(papers, [], readings, inventory)
        self.assertTrue(snapshot["completion_gate"]["satisfied"])
        self.assertEqual(snapshot["entry_reading_depth"]["context"], 1)

    def test_orphan_extraction(self) -> None:
        papers = [{"stable_id": "arxiv:1", "abstract": "a"}]
        index = [
            {"stable_id": "arxiv:1", "status": "full_text_ok"},
            {"stable_id": "arxiv:removed", "status": "full_text_ok"},
        ]
        snapshot = build_coverage_snapshot(papers, index, {}, None)
        self.assertEqual(snapshot["fulltext_extracted"], 1)

    def test_partial_coverage(self) -> None:
        papers = [
            {"stable_id": "arxiv:1", "abstract": "a"},
            {"stable_id": "arxiv:2", "abstract": "b"},
        ]
        index = [
            {"stable_id": "arxiv:1", "status": "full_text_ok"},
            {"stable_id": "arxiv:2", "status": "partial_text"},
        ]

        snapshot = build_coverage_snapshot(papers, index, {}, None)

        self.assertEqual(snapshot["fulltext_extracted"], 1)
        self.assertEqual(snapshot["canonical_paper_fulltext_extraction_coverage"], 0.5)
        self.assertEqual(
            snapshot["extraction_failures"],
            [{"stable_id": "arxiv:2", "status": "partial_text"}],
        )

    def test_public_issue(self) -> None:
        issue = public_extraction_issue(
            {
                "stable_id": "arxiv:1",
                "status": "extract_failed",
                "source_route": "arxiv",
                "error_type": "TimeoutError",
                "error": "local extraction path redacted",
                "text_path": "data/cache/text/private.txt",
                "pdf_url": "https://example.test/private-token",
                "pdf_sha256": "a" * 64,
            }
        )

        self.assertEqual(
            issue,
            {
                "stable_id": "arxiv:1",
                "status": "extract_failed",
                "source_route": "arxiv",
                "error_type": "TimeoutError",
            },
        )

    def test_verified_denominator(self) -> None:
        papers = [
            {"stable_id": "arxiv:1", "abstract": "a"},
            {"stable_id": "urlhash:context", "record_kind": "non_paper_context"},
        ]
        index = [
            {"stable_id": "arxiv:1", "status": "full_text_ok"},
            {"stable_id": "urlhash:context", "status": "full_text_ok"},
        ]
        readings = {"arxiv:1": {"reading_depth": "verified"}}
        inventory = {
            "summary": {
                "canonical_records_classified": 2,
                "paper_records": 1,
                "non_paper_records": 1,
                "adapter_supported": 1,
                "adapter_missing": 0,
                "by_route": {"arxiv": 1, "non_paper": 1},
                "by_extraction_status": {"full_text_ok": 1, "not_applicable": 1},
            },
            "records": [
                {
                    "stable_id": "arxiv:1",
                    "requires_reading": True,
                    "adapter_supported": True,
                },
                {
                    "stable_id": "urlhash:context",
                    "requires_reading": False,
                    "adapter_supported": False,
                },
            ],
        }
        snapshot = build_coverage_snapshot(papers, index, readings, inventory)
        self.assertEqual(snapshot["entry_reading_depth"]["verified"], 1)
        self.assertEqual(snapshot["fulltext_extracted"], 1)
        self.assertEqual(snapshot["canonical_paper_fulltext_extraction_coverage"], 1.0)
        self.assertEqual(snapshot["canonical_paper_full_reading_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
