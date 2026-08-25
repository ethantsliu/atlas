"""Normalize evidence identity across PDF and alternate document sources."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_FORMATS = {"pdf", "html"}
CACHE_HOST = "scholar.googleusercontent.com"
CACHE_QUERY = re.compile(r"^cache:[^:\s]+(?::.*)?$")
CACHE_QUERY_FIELDS = {"q", "hl", "as_sdt"}


def query_values(query: str, allowed: set[str]) -> dict[str, str] | None:
    """Return unique, nonblank query values when every key is allowed."""
    pairs = parse_qsl(query, keep_blank_values=True)
    values: dict[str, str] = {}
    for key, value in pairs:
        if key not in allowed or not value or key in values:
            return None
        values[key] = value
    return values


def source_format(entry: dict) -> str:
    """Return the explicit format, treating legacy PDF records as PDF."""
    return entry.get("source_format", "pdf")


def source_hash(entry: dict) -> str:
    """Return the byte hash that pins the reviewed source artifact."""
    if source_format(entry) == "pdf":
        return entry.get("pdf_sha256", "")
    return entry.get("source_sha256", "")


def is_cache_url(value: str) -> bool:
    """Recognize the single approved public Scholar-cache URL shape."""
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    query = query_values(parsed.query, CACHE_QUERY_FIELDS)
    return (
        parsed.scheme == "https"
        and parsed.netloc == CACHE_HOST
        and parsed.path == "/scholar"
        and not parsed.fragment
        and query is not None
        and bool(CACHE_QUERY.fullmatch(query.get("q", "")))
    )


def valid_html(entry: dict) -> bool:
    """Require the audited cache route for an HTML evidence artifact."""
    stable_id = entry.get("stable_id", "")
    origin_url = entry.get("origin_url", "")
    if not isinstance(stable_id, str) or not stable_id.startswith("openreview:"):
        return False
    if not isinstance(origin_url, str):
        return False
    origin = urlsplit(origin_url)
    expected = stable_id.removeprefix("openreview:")
    origin_query = query_values(origin.query, {"id"})
    return (
        is_cache_url(entry.get("source_url", ""))
        and entry.get("download_adapter") == "scholar_html"
        and (entry.get("source_route") or entry.get("route")) == "source_override"
        and origin.scheme == "https"
        and origin.netloc == "openreview.net"
        and origin.path in {"/forum", "/pdf"}
        and not origin.fragment
        and origin_query == {"id": expected}
    )


def route_identity(
    entry: dict,
) -> tuple[str | None, str | None, str | None, str | None, str | None, str]:
    """Normalize route fields across resolved sources and legacy index rows."""
    route = entry.get("source_route") or entry.get("route")
    pdf_url = entry.get("pdf_url")
    if not route and entry.get("arxiv_id"):
        route = "arxiv"
    if not pdf_url and entry.get("arxiv_id"):
        pdf_url = f"https://export.arxiv.org/pdf/{entry['arxiv_id']}"
    return (
        route,
        entry.get("source_url"),
        entry.get("origin_url"),
        pdf_url,
        entry.get("download_adapter"),
        source_format(entry),
    )


def same_route(left: dict, right: dict) -> bool:
    """Compare normalized retrieval identity without content hashes."""
    return route_identity(left) == route_identity(right)


def valid_source(entry: dict) -> bool:
    """Validate one unambiguous source-format and hash pairing."""
    format_name = source_format(entry)
    if format_name not in SOURCE_FORMATS or not SHA256.fullmatch(source_hash(entry)):
        return False
    if format_name == "pdf":
        return "source_sha256" not in entry and "source_format" not in entry
    return "pdf_sha256" not in entry and "source_format" in entry and valid_html(entry)
