"""Keep published research artifacts free of local execution identity."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterator

from rules import check


PUBLIC_REVIEWER = re.compile(r"^reviewer-[0-9a-f]{12}$")
LOCAL_PATH = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:/(?:root)(?:/|\b)|/(?:users|home)/[^/\s]+/|"
    r"[a-z]:\\users\\[^\\\s]+\\)"
)
PERSONAL_SOCIAL = re.compile(
    r"(?i)https?://(?:mobile\.)?(?:twitter\.com|x\.com)/[a-z0-9_]+"
)
PRIVATE_REVIEWER = re.compile(
    r"(?i)(?:fleet|codex|" + re.escape("/" + "root/") + r"|corpus-reading)"
)
EMAIL = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"(?![a-z0-9.-])"
)
HANDLE = re.compile(r"(?i)(?<![a-z0-9_])@[a-z0-9_]{2,32}(?![a-z0-9_])")
FILE_URI = re.compile(r"(?i)(?:^|[^a-z0-9])file://")
DEVICE_PATH = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:\.\.?[/\\]|~[/\\]|/(?:etc|mnt|opt|private|"
    r"root|tmp|var|volumes|workspace)(?:/|\b)|[a-z]:[/\\](?:users|"
    r"documents and settings)(?:[/\\]|\b))"
)
LOCAL_URL = re.compile(
    r"(?i)https?://(?:localhost|0(?:\.0){3}|127(?:\.\d{1,3}){3}|"
    r"10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
    r"169\.254(?:\.\d{1,3}){2}|\[?::1\]?|[a-z0-9.-]+\.local)"
    r"(?::\d+)?(?:[/\s]|$)"
)
SOCIAL_URL = re.compile(
    r"(?i)https?://(?:www\.|mobile\.)?(?:bsky\.app|bitbucket\.org|discord\.com|"
    r"discord\.gg|facebook\.com|github\.com|gitlab\.com|instagram\.com|"
    r"linkedin\.com|mastodon\.[a-z.]+|medium\.com|reddit\.com|substack\.com|"
    r"t\.me|telegram\.me|threads\.net|tiktok\.com|twitch\.tv|twitter\.com|"
    r"weibo\.com|x\.com|youtube\.com|youtu\.be)/"
)
PRIVATE_CONTEXT = re.compile(
    r"(?i)(?:\b(?:private|personal|local)[\s_-]+"
    r"(?:repo(?:sitory)?|project|device|machine|workspace)\b|"
    r"\b(?:device|machine|workspace)[\s_-]+(?:id|name|path)\b|"
    r"\bhost[\s_-]*name[\s:=]+|\b[a-z0-9]+[-_]overleaf\b|"
    r"\b(?:codex|fleet|corpus-reading)[\s_-]+(?:agent|reviewer|workspace)\b)"
)
UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


def public_reviewer_id(stable_id: str, checked_at: str) -> str:
    """Derive an opaque, repeatable identifier for one verification event."""
    payload = f"atlas-public-reviewer-v1\0{stable_id}\0{checked_at}".encode()
    return f"reviewer-{hashlib.sha256(payload).hexdigest()[:12]}"


def unsafe_public(text: str) -> bool:
    """Detect contact, device, private-project, and display-control text."""
    value = unicodedata.normalize("NFKC", text)
    return (
        LOCAL_PATH.search(value) is not None
        or DEVICE_PATH.search(value) is not None
        or FILE_URI.search(value) is not None
        or EMAIL.search(value) is not None
        or HANDLE.search(value) is not None
        or PERSONAL_SOCIAL.search(value) is not None
        or SOCIAL_URL.search(value) is not None
        or LOCAL_URL.search(value) is not None
        or PRIVATE_CONTEXT.search(value) is not None
        or any(
            unicodedata.category(character) in UNSAFE_CATEGORIES for character in text
        )
    )


def text_values(value: object) -> Iterator[tuple[str, str]]:
    """Yield dotted locations and string values from a JSON-compatible tree."""
    pending: list[tuple[str, object]] = [("$", value)]
    while pending:
        location, current = pending.pop()
        if isinstance(current, str):
            yield location, current
        elif isinstance(current, dict):
            pending.extend((f"{location}.{key}", item) for key, item in current.items())
        elif isinstance(current, list):
            pending.extend(
                (f"{location}[{index}]", item) for index, item in enumerate(current)
            )


def validate_public(value: object, label: str) -> None:
    """Reject machine paths, personal social links, and internal reviewer labels."""
    for location, text in text_values(value):
        check(
            LOCAL_PATH.search(text) is None,
            f"{label} contains a local device path at {location}",
        )
        check(
            PERSONAL_SOCIAL.search(text) is None,
            f"{label} contains a personal social URL at {location}",
        )
        if location.endswith(".reviewer_id"):
            check(
                bool(PUBLIC_REVIEWER.fullmatch(text))
                and PRIVATE_REVIEWER.search(text) is None,
                f"{label} contains a private reviewer ID at {location}",
            )
