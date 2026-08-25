#!/usr/bin/env python3
"""Recover unreadable PDF pages with local OCR while preserving native text."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from extract import (
    INDEX,
    ROOT,
    load_index,
    same_source_revision,
    save_index,
)
from files import atomic_write_text
from identity import source_format
from pages import PageGapAuditIndex, load_page_audits
from quality import (
    PAGE_GAP_AUDIT_QUALITY_FIELDS,
    PAGE_MARKER,
    apply_page_audit,
    assess_text_quality,
    read_cached_text,
)

DEFAULT_DPI = 220


def split_page_text(text: str, page_count: int) -> list[str]:
    """Return exactly one native-text body per indexed PDF page."""
    bodies = [body.strip() for body in PAGE_MARKER.split(text)[1:]]
    return (bodies + [""] * page_count)[:page_count]


def format_page_text(page_bodies: list[str]) -> str:
    """Serialize page bodies using the same stable marker format as extraction."""
    chunks = [
        f"\n\n<<<PAGE {page_number}>>>\n\n{body.strip()}"
        for page_number, body in enumerate(page_bodies, start=1)
    ]
    return "".join(chunks).strip() + "\n"


def merge_ocr_text(
    native_text: str,
    page_count: int,
    ocr_by_page: dict[int, str],
) -> str:
    """Replace only requested pages that yielded non-empty OCR output."""
    bodies = split_page_text(native_text, page_count)
    for page_number, ocr_text in ocr_by_page.items():
        if 1 <= page_number <= page_count and ocr_text.strip():
            bodies[page_number - 1] = ocr_text
    return format_page_text(bodies)


def statuses_to_process(
    include_partial: bool, include_full_gaps: bool = False
) -> set[str]:
    """Keep expensive OCR opt-in for partial extracts and isolated full-text gaps."""
    statuses = {"needs_ocr"}
    if include_partial:
        statuses.update({"partial_text", "low_quality"})
    if include_full_gaps:
        statuses.add("full_text_ok")
    return statuses


def unattempted_missing_pages(entry: dict) -> list[int]:
    """Return unreadable pages not already tried against this source revision."""
    attempted = {
        *entry.get("ocr_attempted_pages", []),
        *entry.get("audited_non_content_pages", []),
        *entry.get("audited_short_content_pages", []),
    }
    return [
        page for page in entry.get("missing_text_pages", []) if page not in attempted
    ]


def render_missing_pages(
    pdf_path: Path,
    page_numbers: list[int],
    output_directory: Path,
    dpi: int,
) -> list[Path]:
    """Render only unreadable pages in deterministic order with Ghostscript."""
    output_template = output_directory / "page-%04d.png"
    subprocess.run(
        [
            "gs",
            "-q",
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pnggray",
            f"-r{dpi}",
            f"-sPageList={','.join(str(page) for page in page_numbers)}",
            f"-sOutputFile={output_template}",
            str(pdf_path),
        ],
        check=True,
        capture_output=True,
    )
    rendered = sorted(output_directory.glob("page-*.png"))
    if len(rendered) != len(page_numbers):
        raise RuntimeError(
            f"Rendered {len(rendered)} pages for {len(page_numbers)} OCR requests"
        )
    return rendered


def recognize_pages(
    rendered_pages: list[Path], page_numbers: list[int]
) -> dict[int, str]:
    """Run Tesseract once per rendered page and retain its UTF-8 stdout."""
    recognized = {}
    for page_number, image_path in zip(page_numbers, rendered_pages, strict=True):
        result = subprocess.run(
            ["tesseract", str(image_path), "stdout", "--psm", "3"],
            check=True,
            capture_output=True,
            text=True,
        )
        recognized[page_number] = result.stdout
    return recognized


def cached_paths(entry: dict) -> tuple[Path, Path]:
    """Resolve the paired cache files from the validated relative text path."""
    text_relative = Path(entry["text_path"])
    if text_relative.is_absolute() or ".." in text_relative.parts:
        raise RuntimeError(f"Unsafe OCR text path for {entry['stable_id']}")
    text_path = ROOT / text_relative
    pdf_path = ROOT / "data/cache/pdf" / f"{text_relative.stem}.pdf"
    return pdf_path, text_path


def ocr_entry(
    entry: dict,
    dpi: int = DEFAULT_DPI,
    gaps: PageGapAuditIndex | None = None,
) -> tuple[dict, int]:
    """OCR one indexed record and return its updated metadata and page count."""
    if source_format(entry) != "pdf":
        raise RuntimeError("OCR only supports PDF source artifacts")
    audits = gaps if gaps is not None else load_page_audits()
    pdf_path, text_path = cached_paths(entry)
    if not pdf_path.exists() or not text_path.exists():
        raise RuntimeError(f"OCR cache files are unavailable for {entry['stable_id']}")
    native_text = read_cached_text(text_path)
    native_quality = assess_text_quality(native_text, entry["page_count"])
    page_numbers = [
        page
        for page in native_quality["missing_text_pages"]
        if page not in set(entry.get("ocr_attempted_pages", []))
    ]
    if not page_numbers:
        return entry, 0

    with tempfile.TemporaryDirectory(prefix="atlas-ocr-") as directory:
        rendered = render_missing_pages(
            pdf_path,
            page_numbers,
            Path(directory),
            dpi,
        )
        recognized = recognize_pages(rendered, page_numbers)

    merged_text = merge_ocr_text(native_text, entry["page_count"], recognized)
    quality = assess_text_quality(merged_text, entry["page_count"])
    quality = apply_page_audit(
        quality,
        entry["page_count"],
        entry["stable_id"],
        entry["pdf_sha256"],
        audits,
    )
    prior_without_audit = {
        key: value
        for key, value in entry.items()
        if key not in PAGE_GAP_AUDIT_QUALITY_FIELDS
    }
    current = {
        **prior_without_audit,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "text_extraction_method": "pypdf+tesseract",
        "ocr_attempted_pages": sorted(
            {*entry.get("ocr_attempted_pages", []), *page_numbers}
        ),
        **quality,
    }
    if same_source_revision(entry, current):
        current["processed_at"] = entry["processed_at"]
    atomic_write_text(text_path, merged_text)
    recovered = quality["pages_with_text"] - native_quality["pages_with_text"]
    return current, recovered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--include-partial",
        action="store_true",
        help="OCR missing pages in partial and low-quality native extracts too",
    )
    parser.add_argument(
        "--include-full-gaps",
        action="store_true",
        help="OCR isolated unreadable pages even when overall coverage already passes",
    )
    args = parser.parse_args()
    if args.limit < 1 or args.dpi < 100:
        raise SystemExit("--limit must be positive and --dpi must be at least 100")
    for executable in ("gs", "tesseract"):
        if shutil.which(executable) is None:
            raise SystemExit(f"Required OCR executable is unavailable: {executable}")

    entries = load_index(INDEX)
    gaps = load_page_audits()
    allowed_statuses = statuses_to_process(args.include_partial, args.include_full_gaps)
    candidates = [
        entry
        for entry in entries.values()
        if entry.get("status") in allowed_statuses
        and source_format(entry) == "pdf"
        and entry.get("text_path")
        and unattempted_missing_pages(entry)
    ][: args.limit]
    processed = 0
    failed = 0
    for entry in candidates:
        try:
            updated, recovered_pages = ocr_entry(
                entry,
                args.dpi,
                gaps,
            )
            entries[entry["stable_id"]] = updated
            save_index(entries, INDEX)
            print(
                f"{updated['status']} {entry['stable_id']}: "
                f"recovered {recovered_pages} pages"
            )
        except Exception as exc:
            failed += 1
            print(f"OCR failed {entry['stable_id']}: {type(exc).__name__}")
        processed += 1
    print(
        json.dumps(
            {
                "processed": processed,
                "failed": failed,
                "remaining_eligible": sum(
                    entry.get("status") in allowed_statuses
                    and source_format(entry) == "pdf"
                    and bool(unattempted_missing_pages(entry))
                    for entry in entries.values()
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
