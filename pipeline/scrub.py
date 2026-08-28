"""Remove private locators while preserving public scholarly text."""

from __future__ import annotations

import re
import unicodedata


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
    r"[a-z]:[/\\](?:users|home|tmp|private)[/\\])[^\s<>\"']+"
)
UNC_DEEP = re.compile(
    r"(?i)(?<![a-z0-9:/?=&])\\\\"
    r"(?P<server>[a-z0-9._-]+)[/\\]"
    r"(?P<share>[a-z0-9$._-]+(?: +[a-z0-9$._-]+)*)[/\\]"
    r"(?P<tail>[^\s<>\"']+)"
)
UNC_SPACE = re.compile(
    r"(?i)(?<![a-z0-9:/?=&])\\\\"
    r"(?P<server>[a-z0-9._-]+)[/\\]"
    r"(?P<share>[a-z0-9$._-]+(?: +[a-z0-9$._-]*[a-z0-9$_-])+)"
    r"(?P<trail>[/\\])?(?=$|[<>\"'])"
)
UNC_ROOT = re.compile(
    r"(?i)(?<![a-z0-9:/?=&])\\\\"
    r"(?P<server>[a-z0-9._-]+)[/\\]"
    r"(?P<share>[a-z0-9$._-]+)(?P<trail>[/\\])?"
    r"(?=$|[\s<>\"'.,;:!?)}\]])"
)
SPACED_TLD = r"(?-i:com|edu|gov|int|mil|net|org)"
EMAIL_HOST = (
    r"(?:[a-z0-9.-]+\.[a-z]{2,63}|"
    rf"[a-z0-9.-]*[a-z][a-z0-9.-]+\.\s+{SPACED_TLD}|localhost)"
)
EMAIL_END = r"(?![a-z0-9-]|\.[a-z0-9])"
CONTACT_EMAIL = re.compile(rf"(?i)<?[a-z0-9_.+-]+@{EMAIL_HOST}>?{EMAIL_END}")
ALL_TLD = r"(?:com|edu|gov|int|mil|net|org)"
ALL_HOST = (
    r"(?:[a-z0-9.-]+\.[a-z]{2,63}|"
    rf"[a-z0-9.-]*[a-z][a-z0-9.-]+\.\s+{ALL_TLD}|localhost)"
)
ALL_EMAIL = re.compile(rf"(?i)<?[a-z0-9_.+-]+@{ALL_HOST}>?{EMAIL_END}")
CONTACT_MARK = re.compile(r"(?i)\b(?:contact|correspondence|(?:e-?)?mail)\b")
CONTACT_TAIL = re.compile(
    r"(?i)(?:\bcontact|\bcorrespondence(?:\s+should\s+be\s+addressed\s+to)?|"
    r"\b(?:e-?)?mail)"
    r"\s*[:.,;!?。；：！？]*\s*$"
)
PUNCT_SPACE = re.compile(r"\s+([.,;:!?。；：！？])")
PUNCT_ONLY = re.compile(r"^[.,;:!?。；：！？]+$")
LOCATORS = (
    PRIVATE_URL,
    LOCAL_URL,
    CRED_URL,
    FILE_URI,
    LOCAL_PATH,
)
EMPTY_WRAP = re.compile(r"(?:<\s*>|\(\s*\)|\[\s*\])")
TEX_COMMANDS = frozenset(
    {
        "alpha",
        "bar",
        "beta",
        "delta",
        "epsilon",
        "gamma",
        "lambda",
        "limits",
        "mathbf",
        "mathrm",
        "omega",
        "phi",
        "pi",
        "psi",
        "rho",
        "sigma",
        "sum",
        "tau",
        "theta",
        "vec",
    }
)
TEX_RELATIONS = frozenset(
    {"even", "geq", "in", "leq", "mid", "neq", "nmid", "notin", "odd"}
)
TEX_TAIL = re.compile(r"(?i)^(?P<name>[a-z]+)[}\]),.;:!?]*$")


def clean_space(value: str) -> str:
    """Normalize whitespace and empty wrappers after redaction."""
    return " ".join(EMPTY_WRAP.sub(" ", value).split())


def tex_unc(match: re.Match[str]) -> bool:
    """Recognize narrow adjacent TeX commands that resemble UNC paths."""
    server = match.group("server").lower()
    share = match.group("share").lower()
    tail = match.groupdict().get("tail")
    if tail is None:
        return (
            (len(server) == 1 and share in TEX_RELATIONS)
            or server in TEX_COMMANDS
            and share in TEX_COMMANDS
        )
    tail_match = TEX_TAIL.fullmatch(tail)
    return (
        tail_match is not None
        and server in TEX_COMMANDS
        and share in TEX_COMMANDS
        and tail_match.group("name").lower() in TEX_COMMANDS
    )


def scrub_unc(value: str) -> str:
    """Remove structured UNC roots and paths without deleting known TeX."""
    result = value
    for pattern in (UNC_DEEP, UNC_SPACE, UNC_ROOT):
        result = pattern.sub(
            lambda match: match.group(0) if tex_unc(match) else " ", result
        )
    return result


def has_unc(value: str) -> bool:
    """Report whether a non-TeX UNC candidate remains."""
    return any(
        not tex_unc(match)
        for pattern in (UNC_DEEP, UNC_SPACE, UNC_ROOT)
        for match in pattern.finditer(value)
    )


def scrub_text(value: str) -> str:
    """Remove unsafe locator classes from one scholarly text field."""
    normalized = unicodedata.normalize("NFKC", value)
    source = normalized if has_locator(normalized) else value
    result = scrub_unc(source)
    for pattern in LOCATORS:
        result = pattern.sub(" ", result)
    return clean_space(result) if result != source else source


def scrub_author(value: str) -> str:
    """Remove malformed contact details from one public author name."""
    return scrub_email(value, ALL_EMAIL)


def scrub_all(value: str) -> str:
    """Remove every email and protected locator from public source text."""
    normalized = unicodedata.normalize("NFKC", value)
    return (
        scrub_email(value, ALL_EMAIL)
        if ALL_EMAIL.search(normalized)
        else scrub_text(value)
    )


def scrub_tree(value: object) -> object:
    """Recursively scrub strings before durable public checkpointing."""
    if isinstance(value, str):
        return scrub_all(value)
    if isinstance(value, list):
        return [scrub_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_tree(item) for key, item in value.items()}
    return value


def scrub_authors(values: list[object]) -> list[object]:
    """Scrub string members while preserving invalid members for validation."""
    result: list[object] = []
    for value in values:
        if not isinstance(value, str):
            result.append(value)
            continue
        cleaned = scrub_author(value)
        if cleaned:
            result.append(cleaned)
    return result


def scrub_email(value: str, pattern: re.Pattern[str]) -> str:
    """Remove email matches from one structured public field."""
    normalized = unicodedata.normalize("NFKC", value)
    source = normalized if pattern.search(normalized) else value
    redacted = pattern.sub(" ", source)
    result = clean_space(scrub_text(redacted))
    if redacted != source:
        result = PUNCT_SPACE.sub(r"\1", result)
        result = clean_space(CONTACT_TAIL.sub(" ", result))
        if PUNCT_ONLY.fullmatch(result):
            return ""
        return result.rstrip(" ,;:")
    return result


def scrub_contact(value: str) -> str:
    """Remove context-aware emails from one public comment field."""
    normalized = unicodedata.normalize("NFKC", value)
    pattern = ALL_EMAIL if CONTACT_MARK.search(normalized) else CONTACT_EMAIL
    return scrub_email(value, pattern)


def scrub_paper(value: dict) -> dict:
    """Remove contact details and private locators from public paper text."""
    result = {**value}
    for field in ("title", "abstract"):
        if isinstance(result.get(field), str):
            result[field] = scrub_all(result[field])
    if isinstance(result.get("comment"), str):
        result["comment"] = scrub_contact(result["comment"])
    authors = result.get("authors")
    if isinstance(authors, list):
        result["authors"] = scrub_authors(authors)
    return result


def has_locator(value: str) -> bool:
    """Report whether a protected locator remains in public text."""
    return has_unc(value) or any(
        pattern.search(value) is not None for pattern in LOCATORS
    )
