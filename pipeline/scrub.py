"""Remove private locators while preserving public scholarly text."""

from __future__ import annotations

import re


PRIVATE_URL = re.compile(
    r"(?i)(?:https?://|(?<![a-z0-9.-]))(?:www\.)?overleaf\.com/project/"
    r"[a-z0-9_-]{8,}(?:[/?#][^\s<>\"']*)?"
)
LOCAL_URL = re.compile(
    r"(?i)(?:https?://(?:localhost|127(?:\.\d{1,3}){3}|\[?::1\]?|"
    r"[a-z0-9.-]+\.local)(?=[:/?#]|$)(?::\d+)?"
    r"(?:[/?#][^\s<>\"']*)?|"
    r"(?<![a-z0-9.:-])(?:localhost|127(?:\.\d{1,3}){3}|\[::1\]):\d+"
    r"(?:/[^\s<>\"']*)?)"
)
CRED_URL = re.compile(r"(?i)https?://[^\s/@:]+:[^\s/@]+@[^\s<>\"']+")
FILE_URI = re.compile(r"(?i)file://[^\s<>\"']+")
LOCAL_PATH = re.compile(
    r"(?i)(?<![a-z0-9:/?=&])(?:/(?:users|home|tmp|private)/|"
    r"~/(?:desktop|documents|downloads|library|repos?|projects?|src|code)/|"
    r"[a-z]:[/\\](?:users|home|tmp|private)[/\\]|"
    r"\\\\[a-z0-9._-]+[/\\])[^\s<>\"']+"
)
AUTHOR_EMAIL = re.compile(r"(?i)<?[a-z0-9_.+-]+@[a-z0-9.-]+\.\s*[a-z]{2,63}>?")
LOCATORS = (
    PRIVATE_URL,
    LOCAL_URL,
    CRED_URL,
    FILE_URI,
    LOCAL_PATH,
)
EMPTY_WRAP = re.compile(r"(?:<\s*>|\(\s*\)|\[\s*\])")


def clean_space(value: str) -> str:
    """Normalize whitespace and empty wrappers after redaction."""
    return " ".join(EMPTY_WRAP.sub(" ", value).split())


def scrub_text(value: str) -> str:
    """Remove unsafe locator classes from one scholarly text field."""
    result = value
    for pattern in LOCATORS:
        result = pattern.sub(" ", result)
    return clean_space(result) if result != value else value


def scrub_author(value: str) -> str:
    """Remove malformed contact details from one public author name."""
    return clean_space(scrub_text(AUTHOR_EMAIL.sub(" ", value)))


def has_locator(value: str) -> bool:
    """Report whether a protected locator remains in public text."""
    return any(pattern.search(value) is not None for pattern in LOCATORS)
