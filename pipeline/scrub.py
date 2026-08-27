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
AUTHOR_EMAIL = re.compile(r"(?i)<?[a-z0-9_.+-]+@[a-z0-9.-]+\.\s*[a-z]{2,63}>?")
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
    result = scrub_unc(value)
    for pattern in LOCATORS:
        result = pattern.sub(" ", result)
    return clean_space(result) if result != value else value


def scrub_author(value: str) -> str:
    """Remove malformed contact details from one public author name."""
    return clean_space(scrub_text(AUTHOR_EMAIL.sub(" ", value)))


def has_locator(value: str) -> bool:
    """Report whether a protected locator remains in public text."""
    return has_unc(value) or any(
        pattern.search(value) is not None for pattern in LOCATORS
    )
