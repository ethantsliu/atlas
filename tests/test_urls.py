from __future__ import annotations

import sys
import unittest
from pathlib import Path
from urllib.request import Request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from urls import (  # noqa: E402
    SafeRedirect,
    is_public_url,
    open_safe,
    read_limited,
    require_public_url,
)


class Response:
    def __init__(
        self,
        body: bytes,
        length: str | None = None,
        url: str = "https://papers.example.org/paper.pdf",
    ) -> None:
        self.body = body
        self.offset = 0
        self.url = url
        self.closed = False
        self.headers = {} if length is None else {"Content-Length": length}

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self.closed = True


class PublicUrlTests(unittest.TestCase):
    def test_https_policy(self) -> None:
        self.assertTrue(is_public_url("https://papers.example.org/paper.pdf"))
        self.assertFalse(is_public_url("http://papers.example.org/paper.pdf"))
        self.assertFalse(is_public_url("https://user@papers.example.org/paper.pdf"))
        self.assertFalse(is_public_url("https://papers.example.org:8443/paper.pdf"))

    def test_private_block(self) -> None:
        for url in (
            "https://127.0.0.1/paper.pdf",
            "https://169.254.169.254/paper.pdf",
            "https://localhost/paper.pdf",
            "file:///tmp/paper.pdf",
        ):
            self.assertFalse(is_public_url(url), url)

    def test_dns_block(self) -> None:
        with patch("urls.public_host", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "outside public IP"):
                require_public_url("https://papers.example.org/paper.pdf")

    def test_redirect_block(self) -> None:
        handler = SafeRedirect()
        with self.assertRaisesRegex(RuntimeError, "public HTTPS"):
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "https://127.0.0.1/private.pdf",
            )

    def test_final_block(self) -> None:
        response = Response(b"private", url="https://127.0.0.1/private")
        opener = type("Opener", (), {"open": lambda *_args, **_kwargs: response})()
        request = Request("https://papers.example.org/paper.pdf")
        with (
            patch("urls.public_host", return_value=True),
            self.assertRaisesRegex(RuntimeError, "public HTTPS"),
        ):
            open_safe(opener, request, 10)
        self.assertTrue(response.closed)

    def test_limited_read(self) -> None:
        self.assertEqual(read_limited(Response(b"paper"), 5), b"paper")
        with self.assertRaisesRegex(RuntimeError, "exceeds"):
            read_limited(Response(b"oversized"), 4)
        with self.assertRaisesRegex(RuntimeError, "Content-Length"):
            read_limited(Response(b"x", "invalid"), 4)


if __name__ == "__main__":
    unittest.main()
