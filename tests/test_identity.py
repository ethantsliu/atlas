from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from identity import is_cache_url, source_format, source_hash, valid_source  # noqa: E402


class SourceIdentityTests(unittest.TestCase):
    def test_cache_url(self) -> None:
        valid = (
            "https://scholar.googleusercontent.com/scholar?"
            "q=cache:abc:scholar.google.com/+%22Exact+Title%22&hl=en&as_sdt=0,5"
        )
        self.assertTrue(is_cache_url(valid))
        for value in (
            "http://scholar.googleusercontent.com/scholar?q=cache:abc",
            "https://example.com/scholar?q=cache:abc",
            "https://scholar.googleusercontent.com:443/scholar?q=cache:abc",
            "https://scholar.googleusercontent.com/cache?q=cache:abc",
            "https://scholar.googleusercontent.com/scholar;other?q=cache:abc",
            "https://scholar.googleusercontent.com/scholar",
            "https://scholar.googleusercontent.com/scholar?q=",
            "https://scholar.googleusercontent.com/scholar?q=cache:",
            "https://scholar.googleusercontent.com/scholar?q=title:abc",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc&q=cache:def",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc&extra=1",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc#fragment",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc&hl=",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc&hl=en&hl=fr",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_cache_url(value))

    def test_legacy_pdf(self) -> None:
        entry = {"pdf_sha256": "a" * 64}

        self.assertEqual(source_format(entry), "pdf")
        self.assertEqual(source_hash(entry), "a" * 64)
        self.assertTrue(valid_source(entry))

    def test_html_source(self) -> None:
        entry = {
            "source_format": "html",
            "source_sha256": "b" * 64,
            "source_route": "source_override",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=abc_DEF",
            "stable_id": "openreview:abc_DEF",
            "download_adapter": "scholar_html",
        }

        self.assertEqual(source_hash(entry), "b" * 64)
        self.assertTrue(valid_source(entry))

    def test_mixed_source(self) -> None:
        entry = {
            "source_format": "html",
            "source_sha256": "b" * 64,
            "pdf_sha256": "a" * 64,
            "source_route": "source_override",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=abc_DEF",
            "stable_id": "openreview:abc_DEF",
            "download_adapter": "scholar_html",
        }

        self.assertFalse(valid_source(entry))

    def test_missing_hash(self) -> None:
        self.assertFalse(valid_source({"source_format": "html"}))
        self.assertFalse(valid_source({}))

    def test_html_route(self) -> None:
        entry = {
            "source_format": "html",
            "source_sha256": "b" * 64,
            "source_route": "source_override",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=abc_DEF",
            "stable_id": "openreview:abc_DEF",
            "download_adapter": "scholar_html",
        }
        for field, value in (
            ("source_url", "https://example.com/scholar?q=cache:abc"),
            ("origin_url", "https://openreview.net/pdf?id=wrong"),
            ("download_adapter", "wrong"),
            ("source_route", "openreview"),
        ):
            changed = {**entry, field: value}
            with self.subTest(field=field):
                self.assertFalse(valid_source(changed))

        for origin_url in (
            "http://openreview.net/pdf?id=abc_DEF",
            "https://openreview.net:443/pdf?id=abc_DEF",
            "https://openreview.net/revisions?id=abc_DEF",
            "https://openreview.net/pdf;other?id=abc_DEF",
            "https://openreview.net/pdf",
            "https://openreview.net/pdf?id=abc_DEF&id=abc_DEF",
            "https://openreview.net/pdf?id=abc_DEF&extra=1",
            "https://openreview.net/pdf?id=abc_DEF#fragment",
        ):
            with self.subTest(origin_url=origin_url):
                self.assertFalse(valid_source({**entry, "origin_url": origin_url}))

    def test_html_id(self) -> None:
        entry = {
            "source_format": "html",
            "source_sha256": "b" * 64,
            "source_route": "source_override",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=arxiv:abc",
            "stable_id": "arxiv:abc",
            "download_adapter": "scholar_html",
        }

        self.assertFalse(valid_source(entry))


if __name__ == "__main__":
    unittest.main()
