from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from lineage import pin_readings, provenance_for, source_locator  # noqa: E402


class ReadingProvenanceTests(unittest.TestCase):
    def test_source_lineage(self) -> None:
        entry = {
            "stable_id": "arxiv:1",
            "arxiv_id": "1",
            "pdf_sha256": "a" * 64,
            "text_sha256": "b" * 64,
            "page_count": 8,
            "processed_at": "2026-08-23T00:00:00+00:00",
        }

        provenance = provenance_for(entry, "verified")

        self.assertEqual(provenance["pdf_sha256"], "a" * 64)
        self.assertEqual(provenance["text_sha256"], "b" * 64)
        self.assertEqual(provenance["review_pass"], "secondary-verified-v1")
        self.assertEqual(source_locator(entry), "https://arxiv.org/pdf/1")

    def test_html_lineage(self) -> None:
        entry = {
            "stable_id": "openreview:abc_DEF",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=abc_DEF",
            "source_format": "html",
            "source_sha256": "c" * 64,
            "source_route": "source_override",
            "download_adapter": "scholar_html",
            "text_sha256": "d" * 64,
            "page_count": 20,
            "processed_at": "2026-08-23T00:00:00+00:00",
        }

        provenance = provenance_for(entry, "full_text")

        self.assertEqual(provenance["source_format"], "html")
        self.assertEqual(provenance["source_sha256"], "c" * 64)
        self.assertNotIn("pdf_sha256", provenance)
        self.assertEqual(source_locator(entry), entry["source_url"])

    def test_mixed_atomic(self) -> None:
        entry = {
            "stable_id": "openreview:abc_DEF",
            "status": "full_text_ok",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=abc_DEF",
            "source_format": "html",
            "source_sha256": "c" * 64,
            "pdf_sha256": "a" * 64,
            "source_route": "source_override",
            "download_adapter": "scholar_html",
            "text_sha256": "d" * 64,
            "page_count": 20,
            "processed_at": "2026-08-23T00:00:00+00:00",
        }
        reading = {
            "stable_id": "openreview:abc_DEF",
            "reading_depth": "full_text",
            "question": "Does the source remain untouched?",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readings = root / "readings"
            readings.mkdir()
            reading_path = readings / "paper.json"
            index_path = root / "index.jsonl"
            original = json.dumps(reading, indent=2) + "\n"
            reading_path.write_text(original, encoding="utf-8")
            index_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not valid"):
                pin_readings(readings, index_path)

            self.assertEqual(reading_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
