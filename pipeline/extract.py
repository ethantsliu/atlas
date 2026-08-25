#!/usr/bin/env python3
"""Retrieve supported evidence artifacts and extract page-bounded text."""

from __future__ import annotations

import argparse
from io import BytesIO
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, filters
from files import atomic_write_bytes, atomic_write_text
from identity import same_route, source_format
from pages import PageGapAuditIndex, load_page_audits
from quality import (
    PAGE_GAP_AUDIT_QUALITY_FIELDS,
    apply_page_audit,
    assess_text_quality,
    read_cached_text,
)
from scholar import extract_cache, fetch_cache, load_cache, verify_cache, verify_link
from sources import select_sources
from urls import open_public, read_limited

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "data/generated/papers_enriched.json"
CACHE = ROOT / "data/cache"
INDEX = ROOT / "data/generated/fulltext_index.jsonl"
USER_AGENT = "atlas/0.1 (research index; cached; contact via local owner)"
AUDITED_WAYBACK_POSTSCRIPT_HOST = "web.archive.org"
AUDITED_WAYBACK_POSTSCRIPT_PATH = (
    "/web/20150403104837id_/http://staff.itee.uq.edu.au/"
    "marcusg/papers/gallagher_acnn98.ps.gz"
)
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_PDF_PAGES = 1000
MAX_PAGE_CHARS = 2_000_000
MAX_TEXT_CHARS = 50_000_000
MAX_STREAM_BYTES = 75_000_000
PDF_LIMIT_FIELDS = (
    "JBIG2_MAX_OUTPUT_LENGTH",
    "LZW_MAX_OUTPUT_LENGTH",
    "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
    "MAX_DECLARED_STREAM_LENGTH",
    "RUN_LENGTH_MAX_OUTPUT_LENGTH",
    "ZLIB_MAX_OUTPUT_LENGTH",
)


def limit_pdf() -> None:
    """Keep pypdf stream decompression limits finite across dependency versions."""
    for field in PDF_LIMIT_FIELDS:
        current = getattr(filters, field, MAX_STREAM_BYTES)
        if not isinstance(current, int) or current <= 0:
            setattr(filters, field, MAX_STREAM_BYTES)
        else:
            setattr(filters, field, min(current, MAX_STREAM_BYTES))


def stream_pdf(response, destination: Path) -> None:
    """Stream one bounded PDF response into an atomic destination."""
    declared = response.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) > MAX_SOURCE_BYTES:
                raise RuntimeError(f"PDF exceeds {MAX_SOURCE_BYTES} bytes")
        except ValueError as error:
            raise RuntimeError("PDF response has invalid Content-Length") from error
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    total = 0
    prefix = b""
    try:
        with os.fdopen(descriptor, "wb") as handle:
            while True:
                chunk = response.read(65_536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise RuntimeError(f"PDF exceeds {MAX_SOURCE_BYTES} bytes")
                if len(prefix) < 5:
                    prefix = (prefix + chunk)[:5]
                handle.write(chunk)
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not prefix.startswith(b"%PDF"):
                raise RuntimeError(f"Expected PDF, received {content_type}")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def decompress_gzip(compressed: bytes) -> bytes:
    """Decompress the audited PostScript response with an output ceiling."""
    try:
        with gzip.GzipFile(fileobj=BytesIO(compressed)) as archive:
            postscript = archive.read(MAX_SOURCE_BYTES + 1)
    except gzip.BadGzipFile as exc:
        raise RuntimeError("Expected a gzip-compressed PostScript source") from exc
    if len(postscript) > MAX_SOURCE_BYTES:
        raise RuntimeError(f"PostScript exceeds {MAX_SOURCE_BYTES} bytes")
    return postscript


def load_index(path: Path = INDEX) -> dict[str, dict]:
    """Load restart state keyed by canonical paper ID."""
    if not path.exists():
        return {}
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            entries[item["stable_id"]] = item
    return entries


def save_index(entries: dict[str, dict], path: Path = INDEX) -> None:
    """Atomically persist deterministic restart state."""
    ordered = sorted(entries.values(), key=lambda item: item["stable_id"])
    atomic_write_text(
        path,
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in ordered),
    )


def fetch_pdf(
    url: str,
    destination: Path,
    download_adapter: str | None = None,
) -> None:
    """Fetch a PDF, resolving explicitly audited dynamic repository links."""
    if download_adapter == "nva_filelink":
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.nva.unit.no":
            raise RuntimeError("NVA file-link adapter requires the official API host")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with open_public(request, timeout=180) as response:
            payload = json.loads(read_limited(response, MAX_METADATA_BYTES))
        resolved_url = payload.get("id", "")
        resolved = urlparse(resolved_url)
        if resolved.scheme != "https" or not resolved.netloc.endswith(
            ".s3.eu-west-1.amazonaws.com"
        ):
            raise RuntimeError(
                "NVA file-link response did not contain an approved PDF host"
            )
        url = resolved_url
    elif download_adapter == "wayback_gzip_postscript":
        fetch_postscript(url, destination)
        return
    elif download_adapter is not None:
        raise RuntimeError(f"Unknown source download adapter: {download_adapter}")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    with open_public(request, timeout=180) as response:
        stream_pdf(response, destination)


def fetch_postscript(url: str, destination: Path) -> None:
    """Convert one audited author-archive PostScript capture to a local PDF."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != AUDITED_WAYBACK_POSTSCRIPT_HOST
        or parsed.path != AUDITED_WAYBACK_POSTSCRIPT_PATH
    ):
        raise RuntimeError(
            "PostScript adapter requires the audited author-archive Memento"
        )

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with open_public(request, timeout=180) as response:
        compressed = read_limited(response, MAX_SOURCE_BYTES)
    postscript = decompress_gzip(compressed)
    if not postscript.lstrip().startswith(b"%!"):
        raise RuntimeError("Decompressed source is not PostScript")

    with tempfile.TemporaryDirectory(prefix="atlas-postscript-") as directory:
        work_directory = Path(directory)
        postscript_path = work_directory / "source.ps"
        rendered_path = work_directory / "rendered.pdf"
        postscript_path.write_bytes(postscript)
        subprocess.run(
            [
                "gs",
                "-dSAFER",
                "-dBATCH",
                "-dNOPAUSE",
                "-sDEVICE=pdfwrite",
                f"-sOutputFile={rendered_path}",
                str(postscript_path),
            ],
            check=True,
            capture_output=True,
        )
        rendered = rendered_path.read_bytes()
    if not rendered.startswith(b"%PDF"):
        raise RuntimeError("Ghostscript did not produce a PDF")
    temporary = destination.with_suffix(".partial")
    atomic_write_bytes(temporary, rendered)
    temporary.replace(destination)


def same_source_revision(left: dict | None, right: dict) -> bool:
    """Compare evidence identity without treating extraction wall-clock as content."""
    if not left:
        return False
    revision_fields = (
        "stable_id",
        "source_route",
        "source_url",
        "origin_url",
        "pdf_url",
        "download_adapter",
        "source_format",
        "pdf_sha256",
        "source_sha256",
        "text_sha256",
        "page_count",
    )
    return all(left.get(field) == right.get(field) for field in revision_fields)


def extract(pdf_path: Path, text_path: Path) -> tuple[int, dict]:
    if pdf_path.stat().st_size > MAX_SOURCE_BYTES:
        raise RuntimeError(f"PDF exceeds {MAX_SOURCE_BYTES} bytes")
    limit_pdf()
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise RuntimeError(f"PDF exceeds {MAX_PDF_PAGES} pages")
    pages = []
    text_size = 0
    for index, page in enumerate(reader.pages, start=1):
        body = page.extract_text(extraction_mode="layout") or ""
        if len(body) > MAX_PAGE_CHARS:
            raise RuntimeError(f"PDF page {index} exceeds the text limit")
        rendered = f"\n\n<<<PAGE {index}>>>\n\n{body.strip()}"
        text_size += len(rendered)
        if text_size > MAX_TEXT_CHARS:
            raise RuntimeError("PDF extracted text exceeds the corpus limit")
        pages.append(rendered)
    text = "".join(pages).strip() + "\n"
    atomic_write_text(text_path, text)
    return page_count, assess_text_quality(text, page_count)


def extract_source(
    stable_id: str,
    record: dict,
    source: dict,
    prior: dict | None,
    force_refetch: bool,
    gaps: PageGapAuditIndex,
) -> tuple[dict, bool]:
    """Extract one resolved document while preserving its exact byte identity."""
    safe_id = source["cache_stem"]
    text_path = CACHE / "text" / f"{safe_id}.txt"
    format_name = source_format(source)
    refresh = force_refetch or (prior is not None and not same_route(prior, source))
    fetched = False
    source_fields: dict[str, str] = {}
    if format_name == "html":
        source_url = verify_link(source["source_url"])
        html_path = CACHE / "html" / f"{safe_id}.html"
        if refresh or not html_path.exists():
            source_url = fetch_cache(
                record["title"],
                stable_id,
                html_path,
                source_url,
            )
            fetched = True
        else:
            verify_cache(load_cache(html_path), stable_id)
        page_count = extract_cache(html_path, text_path)
        quality = assess_text_quality(read_cached_text(text_path), page_count)
        source_fields = {
            "source_format": "html",
            "source_url": source_url,
            "source_sha256": hashlib.sha256(load_cache(html_path)).hexdigest(),
        }
    else:
        pdf_path = CACHE / "pdf" / f"{safe_id}.pdf"
        if refresh or not pdf_path.exists():
            fetch_pdf(
                source["pdf_url"],
                pdf_path,
                source.get("download_adapter"),
            )
            fetched = True
        page_count, quality = extract(pdf_path, text_path)
        pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        quality = apply_page_audit(
            quality,
            page_count,
            stable_id,
            pdf_sha256,
            gaps,
        )
        source_fields = {"pdf_sha256": pdf_sha256}
    current = {
        "stable_id": stable_id,
        "source_route": source["route"],
        **source_fields,
        "page_count": page_count,
        "text_path": str(text_path.relative_to(ROOT)),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        **quality,
    }
    if source.get("pdf_url"):
        current["pdf_url"] = source["pdf_url"]
    if source.get("origin_url"):
        current["origin_url"] = source["origin_url"]
    if source.get("download_adapter"):
        current["download_adapter"] = source["download_adapter"]
    if same_source_revision(prior, current):
        current["processed_at"] = prior["processed_at"]
    return current, fetched


def audit_existing_text(
    entries: dict[str, dict],
    gaps: PageGapAuditIndex | None = None,
) -> tuple[int, int]:
    """Backfill integrity metadata for locally available cached text files."""
    audits = gaps if gaps is not None else load_page_audits()
    updated = 0
    missing = 0
    for entry in entries.values():
        text_path_value = entry.get("text_path")
        if not text_path_value:
            continue
        text_path = ROOT / text_path_value
        if not text_path.exists():
            missing += 1
            continue
        text = read_cached_text(text_path)
        quality = assess_text_quality(text, entry.get("page_count", 0))
        if source_format(entry) == "pdf":
            quality = apply_page_audit(
                quality,
                entry.get("page_count", 0),
                entry["stable_id"],
                entry.get("pdf_sha256", ""),
                audits,
            )
        for field in PAGE_GAP_AUDIT_QUALITY_FIELDS:
            entry.pop(field, None)
        entry.update(quality)
        updated += 1
    return updated, missing


def select_candidates(
    sources: dict[str, tuple[dict, dict]],
    *,
    start: int = 0,
    stable_ids: list[str] | None = None,
) -> list[tuple[str, tuple[dict, dict]]]:
    """Select a stable extraction slice or explicit canonical paper IDs."""
    requested = stable_ids or []
    if requested:
        unknown = sorted(set(requested) - sources.keys())
        if unknown:
            raise ValueError(f"Unknown or unsupported stable IDs: {', '.join(unknown)}")
        requested_set = set(requested)
        return [item for item in sources.items() if item[0] in requested_set]
    return list(sources.items())[start:]


def should_process_candidate(
    prior: dict | None,
    *,
    source: dict | None = None,
    retry_failed: bool,
    force_refetch: bool,
    explicitly_selected: bool,
) -> bool:
    """Apply one restart policy to sequential and explicitly targeted runs."""
    if prior is None:
        return True
    route_drifted = source is not None and not same_route(prior, source)
    if (
        prior.get("status") == "full_text_ok"
        and not force_refetch
        and not route_drifted
    ):
        return False
    if route_drifted:
        return True
    return retry_failed or force_refetch or explicitly_selected


def failure_entry(stable_id: str, source: dict, error: Exception) -> dict:
    """Build safe restart metadata without persisting remote error bodies."""
    failed = {
        "stable_id": stable_id,
        "source_route": source["route"],
        "status": "extract_failed",
        "error_type": type(error).__name__,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    for field in (
        "pdf_url",
        "origin_url",
        "source_format",
        "source_url",
        "download_adapter",
    ):
        if source.get(field):
            failed[field] = source[field]
    return failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=25, help="Maximum new records to process"
    )
    parser.add_argument(
        "--delay", type=float, default=3.1, help="Minimum delay after a network fetch"
    )
    parser.add_argument(
        "--start", type=int, default=0, help="Start offset in supported unique papers"
    )
    parser.add_argument(
        "--stable-id",
        action="append",
        default=[],
        help="Process only this canonical ID; repeat for multiple IDs",
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--force-refetch",
        action="store_true",
        help="Replace a cached document from its resolved source before extraction",
    )
    parser.add_argument(
        "--audit-existing",
        action="store_true",
        help="Backfill hashes and quality metrics for available cached text, then exit",
    )
    args = parser.parse_args()

    records = json.loads(PAPERS.read_text(encoding="utf-8"))
    gaps = load_page_audits()
    unique = select_sources(records)
    if args.start and args.stable_id:
        parser.error("--start cannot be combined with --stable-id")
    try:
        candidates = select_candidates(
            unique,
            start=args.start,
            stable_ids=args.stable_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    entries = load_index()
    if args.audit_existing:
        updated, missing = audit_existing_text(entries, gaps)
        save_index(entries)
        print(f"Audited {updated} cached texts; {missing} cache files unavailable")
        return
    processed = 0
    (CACHE / "pdf").mkdir(parents=True, exist_ok=True)
    (CACHE / "html").mkdir(parents=True, exist_ok=True)
    (CACHE / "text").mkdir(parents=True, exist_ok=True)
    for stable_id, (record, source) in candidates:
        prior = entries.get(stable_id)
        if not should_process_candidate(
            prior,
            source=source,
            retry_failed=args.retry_failed,
            force_refetch=args.force_refetch,
            explicitly_selected=bool(args.stable_id),
        ):
            continue
        if processed >= args.limit:
            break
        fetched = False
        try:
            current, fetched = extract_source(
                stable_id,
                record,
                source,
                prior,
                args.force_refetch,
                gaps,
            )
            entries[stable_id] = current
            print(
                f"{current['status']} {stable_id}: {current['page_count']} pages, "
                f"{current['useful_character_count']:,} useful chars"
            )
        except Exception as exc:
            entries[stable_id] = failure_entry(stable_id, source, exc)
            print(f"failed {stable_id}: {exc}")
        save_index(entries)
        processed += 1
        if fetched and processed < args.limit:
            time.sleep(args.delay)
    print(f"Processed {processed}; index now contains {len(entries)} unique papers")


if __name__ == "__main__":
    main()
