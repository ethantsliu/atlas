from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from scholar import (  # noqa: E402
    cache_text,
    cache_link,
    extract_cache,
    fetch_cache,
    MAX_CACHE_BYTES,
    page_texts,
    query_url,
    verify_cache,
    verify_link,
)


def cache_html(
    page_numbers: tuple[int, ...] = (1, 2),
    short: bool = False,
    origin_url: str = "https://openreview.net/forum?id=abc_DEF",
) -> bytes:
    pages = []
    for number in page_numbers:
        body = (
            "tiny" if short else f"Page {number} has enough useful research text. " * 3
        )
        pages.append(
            f"<table border=0 width=100%><tr><td><b>Page {number}</b></td></tr>"
            f"</table><main>{body}</main>"
        )
    return (
        f'<html><head><base href="{origin_url}"></head>'
        f"<body>{''.join(pages)}</body></html>"
    ).encode()


class ScholarCacheTests(unittest.TestCase):
    def test_exact_query(self) -> None:
        self.assertIn("%22Exact+Paper+Title%22", query_url("Exact Paper Title"))

    def test_link_shape(self) -> None:
        link = (
            "https://scholar.googleusercontent.com/scholar?"
            "q=cache:abc:scholar.google.com/+%22Exact+Title%22&hl=en&as_sdt=0,5"
        )
        self.assertEqual(verify_link(link), link)
        for invalid in (
            "https://example.com/scholar?q=cache:abc",
            "https://scholar.googleusercontent.com/scholar?q=cache:",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc&q=cache:def",
            "https://scholar.googleusercontent.com/scholar?q=cache:abc#fragment",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Invalid Scholar"):
                    verify_link(invalid)

    def test_cache_discovery(self) -> None:
        link = "https://scholar.googleusercontent.com/scholar?q=cache:abc"
        page = f'<a href="https://example.com/no">x</a><a href="{link}">cache</a>'
        self.assertEqual(cache_link(page), link)

    def test_identity(self) -> None:
        verify_cache(cache_html(), "openreview:abc_DEF")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            verify_cache(cache_html(), "openreview:different")
        with self.assertRaisesRegex(RuntimeError, "OpenReview stable ID"):
            verify_cache(cache_html(), "arxiv:abc_DEF")
        with self.assertRaisesRegex(RuntimeError, "missing"):
            verify_cache(b"<html>no base</html>", "openreview:abc_DEF")
        for origin_url in (
            "https://openreview.net/forum?id=abc_DEF&id=abc_DEF",
            "https://openreview.net/forum?id=abc_DEF&extra=1",
            "https://openreview.net/forum?id=abc_DEF#fragment",
            "https://openreview.net/forum;other?id=abc_DEF",
            "https://openreview.net/pdf?id=abc_DEF",
        ):
            with self.subTest(origin_url=origin_url):
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    verify_cache(
                        cache_html(origin_url=origin_url), "openreview:abc_DEF"
                    )

    def test_page_order(self) -> None:
        self.assertEqual(len(page_texts(cache_html())), 2)
        for numbers in ((1, 3), (2, 1)):
            with self.assertRaisesRegex(RuntimeError, "incomplete or unordered"):
                page_texts(cache_html(numbers))

    def test_short_page(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unusable"):
            page_texts(cache_html(short=True))

    def test_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.html"
            destination = Path(directory) / "paper.txt"
            source.write_bytes(cache_html())

            count = extract_cache(source, destination)

            text = destination.read_text()
        self.assertEqual(count, 2)
        self.assertIn("<<<PAGE 1>>>", text)
        self.assertIn("<<<PAGE 2>>>", text)
        self.assertEqual(text, cache_text(cache_html()))

    def test_image_alt(self) -> None:
        payload = cache_html().replace(
            b"</main>", b'<img alt="x squared equals y"></main>', 1
        )

        pages = page_texts(payload)

        self.assertIn("x squared equals y", pages[0])

    def test_fetch_limit(self) -> None:
        link = "https://scholar.googleusercontent.com/scholar?q=cache:abc"
        response = type(
            "Response",
            (),
            {
                "headers": {"Content-Length": str(MAX_CACHE_BYTES + 1)},
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
            },
        )()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.html"
            with (
                patch("scholar.safe_opener"),
                patch("scholar.open_safe", return_value=response),
                self.assertRaisesRegex(RuntimeError, "exceeds"),
            ):
                fetch_cache(
                    "Exact Paper Title",
                    "openreview:abc_DEF",
                    destination,
                    link,
                )
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
