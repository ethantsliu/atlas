from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from quality import assess_text_quality  # noqa: E402
from ocr import (  # noqa: E402
    format_page_text,
    merge_ocr_text,
    split_page_text,
    statuses_to_process,
    unattempted_missing_pages,
)


class OcrFullTextTests(unittest.TestCase):
    def test_page_merge(self) -> None:
        native = format_page_text(["native first page", "", "native third page"])

        merged = merge_ocr_text(native, 3, {2: "recovered second page", 3: ""})

        self.assertEqual(
            split_page_text(merged, 3),
            ["native first page", "recovered second page", "native third page"],
        )

    def test_ocr_quality(self) -> None:
        text = format_page_text(
            ["A substantive recovered research page 123. " * 40 for _ in range(2)]
        )

        quality = assess_text_quality(text, 2)

        self.assertEqual(quality["status"], "full_text_ok")
        self.assertEqual(quality["missing_text_pages"], [])

    def test_partial_optin(self) -> None:
        self.assertEqual(statuses_to_process(False), {"needs_ocr"})
        self.assertEqual(
            statuses_to_process(True),
            {"needs_ocr", "partial_text", "low_quality"},
        )
        self.assertEqual(
            statuses_to_process(False, include_full_gaps=True),
            {"needs_ocr", "full_text_ok"},
        )

    def test_zero_progress(self) -> None:
        entry = {
            "missing_text_pages": [2, 4, 5],
            "ocr_attempted_pages": [2, 5],
            "audited_non_content_pages": [4],
            "audited_short_content_pages": [],
        }

        self.assertEqual(unattempted_missing_pages(entry), [])


if __name__ == "__main__":
    unittest.main()
