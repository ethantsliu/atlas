"""Keep published research artifacts free of local execution identity."""

from __future__ import annotations

import hashlib
import re
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


def public_reviewer_id(stable_id: str, checked_at: str) -> str:
    """Derive an opaque, repeatable identifier for one verification event."""
    payload = f"atlas-public-reviewer-v1\0{stable_id}\0{checked_at}".encode()
    return f"reviewer-{hashlib.sha256(payload).hexdigest()[:12]}"


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
