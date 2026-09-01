"""Reject curator annotations and malformed text in scholarly titles."""

from __future__ import annotations

import re
import unicodedata


URL = re.compile(r"https?://", re.IGNORECASE)
BARE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
RULE = re.compile(r"^[\s—–_-]{10,}")
CURATOR = (
    re.compile(r"^READ THIS!", re.IGNORECASE),
    re.compile(r"^Q\d+\s*:"),
    re.compile(r"^Question:\s*\(1\)", re.IGNORECASE),
    re.compile(r"^Comment:\s*:", re.IGNORECASE),
    re.compile(r"THIS IS RELEVANT TO", re.IGNORECASE),
    re.compile(r"ALSO LINK TO:", re.IGNORECASE),
)


def title_issue(value: object, strict: bool = False) -> str | None:
    """Return the first unambiguous public-title defect, if any."""
    if not isinstance(value, str) or not value.strip():
        return "missing title"
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
        return "control text"
    if BARE_URL.fullmatch(value.strip()):
        return "bare URL title"
    if any(pattern.search(value) for pattern in CURATOR):
        return "curator annotation"
    if strict and URL.search(value):
        return "embedded URL"
    if strict and RULE.match(value):
        return "import wrapper"
    return None


def valid_title(value: object, strict: bool = False) -> bool:
    """Return whether a title is safe for the requested public boundary."""
    return title_issue(value, strict) is None
