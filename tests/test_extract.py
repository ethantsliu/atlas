from __future__ import annotations

import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from extract import (  # noqa: E402
    MAX_PDF_PAGES,
    MAX_SOURCE_BYTES,
    decompress_gzip,
    extract,
    fetch_pdf,
    load_index,
    save_index,
    select_candidates,
    should_process_candidate,
    same_source_revision,
)
from quality import (  # noqa: E402
    MIN_REVIEWABLE_PAGE_COVERAGE,
    assess_text_quality,
    classify_text_quality,
    read_cached_text,
)


class FullTextIndexTests(unittest.TestCase):
    class FakeResponse:
        def __init__(
            self,
            body: bytes,
            content_type: str,
            content_length: int | None = None,
        ) -> None:
            self.body = body
            self.offset = 0
            self.headers = {"Content-Type": content_type}
            if content_length is not None:
                self.headers["Content-Length"] = str(content_length)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.body) - self.offset
            start = self.offset
            self.offset = min(len(self.body), start + size)
            return self.body[start : self.offset]

    def test_marker_quality(self) -> None:
        quality = assess_text_quality("<<<PAGE 1>>>\n", 1)
        self.assertEqual(quality["status"], "needs_ocr")
        self.assertEqual(quality["pages_with_text"], 0)

    def test_integrity_metrics(self) -> None:
        text = "<<<PAGE 1>>>\n" + ("A useful research result 123. " * 80)
        quality = assess_text_quality(text, 1)
        self.assertEqual(quality["status"], "full_text_ok")
        self.assertEqual(quality["pages_with_text"], 1)
        self.assertEqual(quality["missing_text_pages"], [])
        self.assertEqual(len(quality["text_sha256"]), 64)

    def test_partial_pages(self) -> None:
        covered_pages = 4
        page_count = 5
        text = "".join(
            f"<<<PAGE {page}>>>\n"
            + (("A useful research result 123. " * 20) if page <= covered_pages else "")
            for page in range(1, page_count + 1)
        )

        quality = assess_text_quality(text, page_count)

        self.assertLess(covered_pages / page_count, MIN_REVIEWABLE_PAGE_COVERAGE)
        self.assertEqual(quality["status"], "partial_text")
        self.assertEqual(quality["missing_text_pages"], [5])

    def test_cache_independence(self) -> None:
        self.assertEqual(classify_text_quality(10_000, 10, 8, 0.8, 0.9), "partial_text")
        self.assertEqual(classify_text_quality(10_000, 10, 9, 0.9, 0.9), "full_text_ok")

    def test_refetch_timestamp(self) -> None:
        prior = {
            "stable_id": "arxiv:1",
            "source_route": "arxiv",
            "pdf_url": "https://arxiv.org/pdf/1",
            "pdf_sha256": "a" * 64,
            "text_sha256": "b" * 64,
            "page_count": 8,
            "processed_at": "first extraction",
        }
        same = {**prior, "processed_at": "later extraction"}
        changed = {**same, "text_sha256": "c" * 64}

        self.assertTrue(same_source_revision(prior, same))
        self.assertFalse(same_source_revision(prior, changed))

    def test_carriage_returns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.txt"
            payload = b"<<<PAGE 1>>>\nline one\rline two\n"
            path.write_bytes(payload)

            restored = read_cached_text(path)

        self.assertEqual(restored.encode("utf-8"), payload)
        self.assertIn("\r", restored)

    def test_index_roundtrip(self) -> None:
        entries = {
            "arxiv:2": {"stable_id": "arxiv:2", "status": "extract_failed"},
            "arxiv:1": {"stable_id": "arxiv:1", "status": "full_text_ok"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            save_index(entries, path)
            restored = load_index(path)
            lines = path.read_text().splitlines()
        self.assertEqual(restored, entries)
        self.assertIn('"stable_id": "arxiv:1"', lines[0])

    def test_candidate_order(self) -> None:
        sources = {
            "arxiv:2": ({"stable_id": "arxiv:2"}, {"route": "arxiv"}),
            "arxiv:1": ({"stable_id": "arxiv:1"}, {"route": "arxiv"}),
        }

        selected = select_candidates(sources, stable_ids=["arxiv:1", "arxiv:2"])

        self.assertEqual(
            [stable_id for stable_id, _ in selected], ["arxiv:2", "arxiv:1"]
        )

    def test_unknown_candidates(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown or unsupported"):
            select_candidates({}, stable_ids=["arxiv:missing"])

    def test_retry_selection(self) -> None:
        failed = {"status": "extract_failed"}
        successful = {"status": "full_text_ok"}

        self.assertTrue(
            should_process_candidate(
                failed,
                retry_failed=False,
                force_refetch=False,
                explicitly_selected=True,
            )
        )
        self.assertFalse(
            should_process_candidate(
                successful,
                retry_failed=True,
                force_refetch=False,
                explicitly_selected=True,
            )
        )

    def test_route_drift(self) -> None:
        prior = {
            "status": "full_text_ok",
            "source_route": "arxiv",
            "pdf_url": "https://export.arxiv.org/pdf/1",
            "pdf_sha256": "a" * 64,
        }
        unchanged = {
            "route": "arxiv",
            "pdf_url": "https://export.arxiv.org/pdf/1",
        }
        changed = {
            "route": "source_override",
            "source_format": "html",
            "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "origin_url": "https://openreview.net/pdf?id=abc",
            "download_adapter": "scholar_html",
        }

        self.assertFalse(
            should_process_candidate(
                prior,
                source=unchanged,
                retry_failed=False,
                force_refetch=False,
                explicitly_selected=False,
            )
        )
        self.assertTrue(
            should_process_candidate(
                prior,
                source=changed,
                retry_failed=False,
                force_refetch=False,
                explicitly_selected=False,
            )
        )

    def test_nva_resolution(self) -> None:
        stable_url = "https://api.nva.unit.no/publication/example/filelink/open-file"
        signed_url = (
            "https://nva-resource-storage-1.s3.eu-west-1.amazonaws.com/file?signature=x"
        )
        responses = [
            self.FakeResponse(
                ('{"id": "' + signed_url + '"}').encode(),
                "application/json",
            ),
            self.FakeResponse(b"%PDF-1.7\nexample", "application/pdf"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "paper.pdf"
            with patch("extract.open_public", side_effect=responses) as opener:
                fetch_pdf(stable_url, destination, "nva_filelink")

            self.assertEqual(destination.read_bytes(), b"%PDF-1.7\nexample")
            self.assertEqual(opener.call_count, 2)
            self.assertEqual(opener.call_args_list[1].args[0].full_url, signed_url)

    def test_nva_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "paper.pdf"
            with self.assertRaisesRegex(RuntimeError, "official API host"):
                fetch_pdf(
                    "https://example.com/filelink/id",
                    destination,
                    "nva_filelink",
                )

    def test_wayback_conversion(self) -> None:
        stable_url = (
            "https://web.archive.org/web/20150403104837id_/"
            "http://staff.itee.uq.edu.au/marcusg/papers/gallagher_acnn98.ps.gz"
        )

        def render_pdf(arguments, **_kwargs) -> None:
            output_argument = next(
                argument
                for argument in arguments
                if argument.startswith("-sOutputFile=")
            )
            Path(output_argument.split("=", 1)[1]).write_bytes(b"%PDF-1.7\nrendered")

        response = self.FakeResponse(
            gzip.compress(b"%!PS-Adobe-3.0\nexample"),
            "application/octet-stream",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "paper.pdf"
            with (
                patch("extract.open_public", return_value=response),
                patch("subprocess.run", side_effect=render_pdf) as renderer,
            ):
                fetch_pdf(
                    stable_url,
                    destination,
                    "wayback_gzip_postscript",
                )

            self.assertEqual(destination.read_bytes(), b"%PDF-1.7\nrendered")
            renderer.assert_called_once()

    def test_wayback_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "paper.pdf"
            with self.assertRaisesRegex(RuntimeError, "audited author-archive"):
                fetch_pdf(
                    "https://web.archive.org/web/20200101000000id_/"
                    "https://example.com/untrusted.ps.gz",
                    destination,
                    "wayback_gzip_postscript",
                )

    def test_pdf_limit(self) -> None:
        response = self.FakeResponse(
            b"%PDF-1.7\n",
            "application/pdf",
            MAX_SOURCE_BYTES + 1,
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "paper.pdf"
            with (
                patch("extract.open_public", return_value=response),
                self.assertRaisesRegex(RuntimeError, "PDF exceeds"),
            ):
                fetch_pdf("https://example.com/paper.pdf", destination)
            self.assertFalse(destination.exists())

    def test_gzip_limit(self) -> None:
        compressed = gzip.compress(b"12345")
        with (
            patch("extract.MAX_SOURCE_BYTES", 4),
            self.assertRaisesRegex(RuntimeError, "PostScript exceeds"),
        ):
            decompress_gzip(compressed)

    def test_page_limit(self) -> None:
        reader = type("Reader", (), {"pages": [object()] * (MAX_PDF_PAGES + 1)})()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\n")
            with (
                patch("extract.PdfReader", return_value=reader),
                self.assertRaisesRegex(RuntimeError, "PDF exceeds .* pages"),
            ):
                extract(pdf_path, root / "paper.txt")


if __name__ == "__main__":
    unittest.main()
