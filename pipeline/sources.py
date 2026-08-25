"""Resolve paper records to supported full-text access routes."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from files import atomic_write_text
from urls import is_public_url


SOURCE_ROUTE_PRIORITY = {
    # An override records a human-audited, identity-preserving source decision.
    "source_override": 100,
    "arxiv": 80,
    "github_pdf": 60,
    "direct_pdf": 50,
    "publisher_pdf": 40,
    "openreview": 30,
}


def _github_raw_url(url: str) -> str | None:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if (
        not is_public_url(url)
        or parsed.netloc.lower() != "github.com"
        or "blob" not in parts
    ):
        return None
    blob_index = parts.index("blob")
    if blob_index < 2 or not parsed.path.lower().endswith(".pdf"):
        return None
    owner, repo = parts[0], parts[1]
    remainder = "/".join(parts[blob_index + 1 :])
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{remainder}"


def override_route(record: dict, stable_id: str) -> dict | None:
    """Resolve one audited alternate source when the record declares it."""
    source_url = record.get("source_url_override")
    if source_url:
        if record.get("source_download_adapter") != "scholar_html":
            raise ValueError("Alternate source overrides require scholar_html")
        if not is_public_url(source_url):
            raise ValueError("Alternate source override must use public HTTPS")
        return {
            "route": "source_override",
            "source_format": "html",
            "source_url": source_url,
            "origin_url": record.get("url", stable_id),
            "cache_stem": stable_id.replace(":", "_").replace("/", "_"),
            "download_adapter": "scholar_html",
        }
    override_url = record.get("pdf_url_override")
    if not override_url:
        return None
    if not is_public_url(override_url):
        raise ValueError("PDF source override must use public HTTPS")
    source = {
        "route": "source_override",
        "pdf_url": override_url,
        "cache_stem": stable_id.replace(":", "_").replace("/", "_"),
    }
    if record.get("source_download_adapter"):
        source["download_adapter"] = record["source_download_adapter"]
    return source


def resolve_source(record: dict) -> dict | None:
    """Return one deterministic document route, or ``None`` for manual review."""
    stable_id = record.get("stable_id", "")
    identifier_kind = record.get("identifier_kind")
    override = override_route(record, stable_id)
    if override:
        return override
    if identifier_kind == "arxiv" and stable_id.startswith("arxiv:"):
        identifier = record.get("arxiv_id") or stable_id.split(":", 1)[1]
        return {
            "route": "arxiv",
            "pdf_url": f"https://export.arxiv.org/pdf/{identifier}",
            "cache_stem": identifier.replace("/", "_"),
        }
    if identifier_kind == "openreview" and stable_id.startswith("openreview:"):
        identifier = stable_id.split(":", 1)[1]
        return {
            "route": "openreview",
            "pdf_url": f"https://openreview.net/pdf?id={identifier}",
            "cache_stem": f"openreview_{identifier}",
        }

    url = record.get("url", "")
    github_url = _github_raw_url(url)
    if github_url:
        return {
            "route": "github_pdf",
            "pdf_url": github_url,
            "cache_stem": stable_id.replace(":", "_").replace("/", "_"),
        }
    if urlparse(url).path.lower().endswith(".pdf"):
        if not is_public_url(url):
            raise ValueError("Direct PDF source must use public HTTPS")
        return {
            "route": "direct_pdf",
            "pdf_url": url,
            "cache_stem": stable_id.replace(":", "_").replace("/", "_"),
        }
    parsed = urlparse(url)
    lowered_path = parsed.path.lower()
    looks_like_publisher_pdf = (
        "/pdf/" in lowered_path
        or "/epdf/" in lowered_path
        or lowered_path.endswith("/pdf")
        or (lowered_path.endswith("/download") and "type=pdf" in parsed.query.lower())
    )
    if looks_like_publisher_pdf:
        if not is_public_url(url):
            raise ValueError("Publisher PDF source must use public HTTPS")
        return {
            "route": "publisher_pdf",
            "pdf_url": url,
            "cache_stem": stable_id.replace(":", "_").replace("/", "_"),
        }
    return None


def select_sources(records: list[dict]) -> dict[str, tuple[dict, dict]]:
    """Choose one deterministic, best-supported source per canonical paper.

    The source collection can mention the same canonical paper more than once.
    A later mention may carry a human-audited override even when the first one
    only has a publisher or OpenReview URL, so blindly keeping the first record
    can discard the stronger source. Equal-priority ties deliberately keep the
    first occurrence to make restarts stable.
    """
    selected: dict[str, tuple[dict, dict]] = {}
    for record in records:
        source = resolve_source(record)
        if source is None:
            continue
        stable_id = record["stable_id"]
        current = selected.get(stable_id)
        if current is None or SOURCE_ROUTE_PRIORITY.get(source["route"], 0) > (
            SOURCE_ROUTE_PRIORITY.get(current[1]["route"], 0)
        ):
            selected[stable_id] = (record, source)
    return selected


def build_source_inventory(papers: list[dict], fulltext_entries: list[dict]) -> dict:
    """Classify every canonical record without claiming every URL is fetchable."""
    prior = {entry["stable_id"]: entry for entry in fulltext_entries}
    selected = select_sources(papers)
    canonical: dict[str, dict] = {}
    for paper in papers:
        canonical.setdefault(paper["stable_id"], paper)

    rows = []
    route_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for stable_id, paper in canonical.items():
        record_kind = paper.get("record_kind", "paper")
        requires_reading = record_kind != "non_paper_context"
        source = selected.get(stable_id, (None, None))[1] if requires_reading else None
        extraction = prior.get(stable_id)
        route = (
            source["route"]
            if source
            else "manual_review"
            if requires_reading
            else "non_paper"
        )
        if not requires_reading:
            status = "not_applicable"
        elif extraction:
            status = extraction.get("status", "unknown")
        elif source:
            status = "pending"
        else:
            status = "adapter_missing"
        route_counts[route] += 1
        status_counts[status] += 1
        rows.append(
            {
                "stable_id": stable_id,
                "route": route,
                "pdf_url": source.get("pdf_url") if source else None,
                "source_url": source.get("source_url") if source else None,
                "origin_url": source.get("origin_url") if source else None,
                "source_format": source.get("source_format", "pdf") if source else None,
                "adapter_supported": source is not None,
                "record_kind": record_kind,
                "requires_reading": requires_reading,
                "extraction_status": status,
            }
        )

    paper_rows = [row for row in rows if row["requires_reading"]]
    supported = sum(row["adapter_supported"] for row in paper_rows)
    summary = {
        "canonical_records_classified": len(rows),
        "paper_records": len(paper_rows),
        "non_paper_records": len(rows) - len(paper_rows),
        "adapter_supported": supported,
        "adapter_missing": len(paper_rows) - supported,
        "by_route": dict(sorted(route_counts.items())),
        "by_extraction_status": dict(sorted(status_counts.items())),
    }
    return {"summary": summary, "records": rows}


def write_source_inventory(path: Path, inventory: dict) -> None:
    """Persist a human-readable access inventory for audit and resumption."""
    atomic_write_text(path, json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
