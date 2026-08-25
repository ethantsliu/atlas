from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from sources import (  # noqa: E402
    build_source_inventory,
    resolve_source,
    select_sources,
)


class PaperSourceTests(unittest.TestCase):
    def test_arxiv_route(self) -> None:
        source = resolve_source(
            {
                "stable_id": "arxiv:2401.00001",
                "identifier_kind": "arxiv",
                "arxiv_id": "2401.00001",
            }
        )
        self.assertEqual(source["route"], "arxiv")
        self.assertTrue(source["pdf_url"].endswith("/2401.00001"))

    def test_openreview_route(self) -> None:
        source = resolve_source(
            {
                "stable_id": "openreview:abc_DEF",
                "identifier_kind": "openreview",
                "url": "https://openreview.net/forum?id=abc_DEF",
            }
        )
        self.assertEqual(source["route"], "openreview")
        self.assertIn("pdf?id=abc_DEF", source["pdf_url"])

    def test_github_route(self) -> None:
        source = resolve_source(
            {
                "stable_id": "urlhash:1",
                "identifier_kind": "urlhash",
                "url": "https://github.com/org/repo/blob/main/paper.pdf",
            }
        )
        self.assertEqual(
            source["pdf_url"],
            "https://raw.githubusercontent.com/org/repo/main/paper.pdf",
        )

    def test_publisher_route(self) -> None:
        source = resolve_source(
            {
                "stable_id": "urlhash:aps",
                "identifier_kind": "urlhash",
                "url": "https://journals.aps.org/pre/pdf/10.1103/example",
            }
        )
        self.assertEqual(source["route"], "publisher_pdf")

    def test_override_route(self) -> None:
        source = resolve_source(
            {
                "stable_id": "doi:example",
                "identifier_kind": "doi",
                "pdf_url_override": "https://example.org/official-paper.pdf",
            }
        )
        self.assertEqual(source["route"], "source_override")
        self.assertEqual(source["pdf_url"], "https://example.org/official-paper.pdf")

    def test_override_adapter(self) -> None:
        source = resolve_source(
            {
                "stable_id": "urlhash:nva",
                "identifier_kind": "urlhash",
                "pdf_url_override": "https://api.nva.unit.no/publication/id/filelink/file",
                "source_download_adapter": "nva_filelink",
            }
        )

        self.assertEqual(source["download_adapter"], "nva_filelink")

    def test_html_override(self) -> None:
        source = resolve_source(
            {
                "stable_id": "openreview:abc_DEF",
                "identifier_kind": "openreview",
                "url": "https://openreview.net/pdf?id=abc_DEF",
                "source_url_override": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
                "source_download_adapter": "scholar_html",
            }
        )

        self.assertEqual(source["source_format"], "html")
        self.assertEqual(source["download_adapter"], "scholar_html")
        self.assertEqual(source["origin_url"], "https://openreview.net/pdf?id=abc_DEF")
        self.assertNotIn("pdf_url", source)

    def test_duplicate_priority(self) -> None:
        records = [
            {
                "stable_id": "openreview:abc_DEF",
                "identifier_kind": "openreview",
                "url": "https://openreview.net/forum?id=abc_DEF",
            },
            {
                "stable_id": "openreview:abc_DEF",
                "identifier_kind": "openreview",
                "pdf_url_override": "https://export.arxiv.org/pdf/2401.00001",
            },
        ]

        selected = select_sources(records)

        self.assertEqual(selected["openreview:abc_DEF"][1]["route"], "source_override")

    def test_tie_order(self) -> None:
        records = [
            {
                "stable_id": "arxiv:2401.00001",
                "identifier_kind": "arxiv",
                "arxiv_id": "2401.00001v1",
            },
            {
                "stable_id": "arxiv:2401.00001",
                "identifier_kind": "arxiv",
                "arxiv_id": "2401.00001v2",
            },
        ]

        selected = select_sources(records)

        self.assertTrue(selected["arxiv:2401.00001"][1]["pdf_url"].endswith("v1"))

    def test_unsupported_record(self) -> None:
        papers = [
            {
                "stable_id": "urlhash:1",
                "identifier_kind": "urlhash",
                "url": "https://example.com/project",
            }
        ]
        inventory = build_source_inventory(papers, [])
        self.assertEqual(inventory["summary"]["adapter_missing"], 1)

    def test_unsafe_pdf(self) -> None:
        with self.assertRaisesRegex(ValueError, "public HTTPS"):
            resolve_source(
                {
                    "stable_id": "urlhash:private",
                    "identifier_kind": "urlhash",
                    "url": "file:///tmp/private.pdf",
                }
            )

    def test_inventory_priority(self) -> None:
        papers = [
            {
                "stable_id": "openreview:abc_DEF",
                "identifier_kind": "openreview",
                "url": "https://openreview.net/forum?id=abc_DEF",
            },
            {
                "stable_id": "openreview:abc_DEF",
                "identifier_kind": "openreview",
                "pdf_url_override": "https://export.arxiv.org/pdf/2401.00001",
            },
        ]

        inventory = build_source_inventory(papers, [])

        self.assertEqual(inventory["records"][0]["route"], "source_override")
        self.assertEqual(inventory["records"][0]["extraction_status"], "pending")

    def test_context_classification(self) -> None:
        papers = [
            {
                "stable_id": "urlhash:context",
                "identifier_kind": "urlhash",
                "record_kind": "non_paper_context",
                "url": "https://example.com/context",
            }
        ]
        inventory = build_source_inventory(papers, [])
        self.assertEqual(inventory["summary"]["non_paper_records"], 1)
        self.assertEqual(inventory["summary"]["adapter_missing"], 0)
        self.assertEqual(inventory["records"][0]["route"], "non_paper")
        self.assertFalse(inventory["records"][0]["requires_reading"])


if __name__ == "__main__":
    unittest.main()
