"""Canonical identifiers for collection records."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlparse

ARXIV_ID = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)", re.IGNORECASE)
OLD_ARXIV_ID = re.compile(
    r"arxiv\.org/(?:pdf|abs)/([a-z.-]+/\d{7})(?:v\d+)?", re.IGNORECASE
)
OPENREVIEW_ID = re.compile(r"^[A-Za-z0-9_-]+")


def canonical_id(record: dict, override: dict | None = None) -> tuple[str, str]:
    """Return a stable identity, honoring an explicit audited source correction."""
    if override and override.get("stable_id") and override.get("identifier_kind"):
        return override["stable_id"], override["identifier_kind"]
    url = record.get("url", "")
    modern = ARXIV_ID.search(url)
    if modern:
        return f"arxiv:{modern.group(1).lower()}", "arxiv"
    old = OLD_ARXIV_ID.search(url)
    if old:
        return f"arxiv:{old.group(1).lower()}", "arxiv"
    parsed = urlparse(url)
    if "openreview.net" in parsed.netloc:
        query = parse_qs(parsed.query)
        note_id = (query.get("id") or [None])[0]
        if note_id:
            clean_id = OPENREVIEW_ID.match(note_id)
            if clean_id:
                return f"openreview:{clean_id.group(0)}", "openreview"
    normalized = f"{parsed.netloc.lower()}{parsed.path.rstrip('/').lower()}"
    digest = hashlib.sha256(
        f"{normalized}\n{record.get('title', '').strip().lower()}".encode()
    ).hexdigest()[:20]
    return f"urlhash:{digest}", "urlhash"
