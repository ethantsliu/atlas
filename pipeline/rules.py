"""Shared evidence-contract primitives for the atlas validators."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlparse

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SOURCE_HOSTS = frozenset(
    json.loads((ROOT / "data/source/hosts.json").read_text(encoding="utf-8"))
)
VERSION_VERIFIED = "version-verified"
LEGACY_UNVERSIONED = "legacy-unversioned"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PMLR_PATH = re.compile(r"^/v(?P<volume>\d+)/(?P<slug>[^/]+?)(?:\.html)?$")
PMLR_ID = re.compile(r"^v?(?P<volume>\d+)[:/-](?P<slug>.+)$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
KIND_HOSTS = {
    "arxiv": {"arxiv.org"},
    "openreview": {"openreview.net"},
    "official-proceedings": {
        "aclanthology.org",
        "arxiv.org",
        "dl.acm.org",
        "ojs.aaai.org",
        "openaccess.thecvf.com",
        "openreview.net",
        "papers.neurips.cc",
        "papers.nips.cc",
        "pldi24.sigplan.org",
        "proceedings.mlr.press",
        "proceedings.neurips.cc",
        "proceedings.nips.cc",
        "www.ijcai.org",
        "www.jmlr.org",
    },
    "publisher": {
        "aclanthology.org",
        "arxiv.org",
        "dl.acm.org",
        "elifesciences.org",
        "journals.aps.org",
        "ojs.aaai.org",
        "openaccess.thecvf.com",
        "papers.neurips.cc",
        "papers.nips.cc",
        "proceedings.mlr.press",
        "proceedings.neurips.cc",
        "www.biorxiv.org",
        "www.jmlr.org",
        "www.nature.com",
        "www.pnas.org",
        "www.science.org",
        "www.sciencedirect.com",
    },
}


def check(condition: bool, message: str) -> None:
    """Raise a readable contract error instead of relying on bare assertions."""
    if not condition:
        raise RuntimeError(message)


def is_primary_url(value: str) -> bool:
    """Accept only the primary archives and proceedings used by reviewed records."""
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in PRIMARY_SOURCE_HOSTS


def source_matches(item: dict) -> bool:
    """Require declared source kind to agree with the primary record host."""
    kind = item.get("source_kind")
    if kind is None:
        return True
    host = urlparse(item["url"]).hostname
    return host in KIND_HOSTS.get(kind, set())


def split_id(value: str) -> tuple[str, str] | None:
    """Split current and retained legacy canonical-ID encodings."""
    prefix, separator, identifier = value.partition(":")
    if separator:
        return prefix, identifier
    for legacy in ("pmlr", "neurips"):
        marker = f"{legacy}-"
        if value.startswith(marker):
            return legacy, value.removeprefix(marker)
    return None


def identity_matches(item: dict) -> bool:
    """Match canonical IDs when their URL exposes the same identifier family."""
    identity = split_id(item["canonical_id"])
    if identity is None:
        return False
    prefix, identifier = identity
    parsed = urlparse(item["url"])
    path = unquote(parsed.path)
    if prefix == "arxiv" and parsed.hostname == "arxiv.org":
        actual = re.sub(
            r"v\d+$",
            "",
            path.removeprefix("/abs/").removeprefix("/pdf/").removesuffix(".pdf"),
        )
        expected = re.sub(r"v\d+$", "", identifier)
        return actual == expected
    if prefix == "openreview" and parsed.hostname == "openreview.net":
        query = parse_qs(parsed.query)
        actual = (query.get("id") or query.get("noteId") or [None])[0]
        if actual is None and path.startswith("/pdf/"):
            actual = path.removeprefix("/pdf/").removesuffix(".pdf")
        return actual == identifier or bool(
            isinstance(actual, str)
            and HEX40.fullmatch(actual)
            and not HEX40.fullmatch(identifier)
        )
    if prefix == "pmlr" and parsed.hostname == "proceedings.mlr.press":
        route = PMLR_PATH.fullmatch(path)
        if route is None:
            return False
        volume, slug = route.group("volume", "slug")
        canonical = PMLR_ID.fullmatch(identifier)
        if canonical is None:
            return identifier == slug
        canonical_volume, canonical_slug = canonical.group("volume", "slug")
        same_slug = canonical_slug == slug or f"a-{canonical_slug}" == slug
        volume_is_explicit = identifier.startswith("v")
        return same_slug and (not volume_is_explicit or canonical_volume == volume)
    return True


def is_iso_date(value: object) -> bool:
    """Accept only unambiguous calendar dates in their canonical form."""
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def is_filled(value: object) -> bool:
    """Accept a string only when it contains visible content."""
    return isinstance(value, str) and bool(value.strip())


def is_sha256(value: object) -> bool:
    """Accept a lowercase hexadecimal SHA-256 digest."""
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def validate_competitor_panel(
    competitors: object,
    *,
    minimum: int,
    label: str,
    excluded_id: str | None = None,
    require_provenance: bool = False,
) -> None:
    """Validate one direct, primary-source related-work panel."""
    check(
        isinstance(competitors, list) and len(competitors) >= minimum,
        f"{label} is incomplete",
    )
    required_fields = ("canonical_id", "title", "url", "relationship", "difference")
    allowed_fields = set(required_fields) | {
        "checked_at",
        "provenance_status",
        "source_date",
        "source_kind",
        "source_version",
    }
    check(
        all(
            isinstance(item, dict)
            and all(
                isinstance(item.get(field), str) and item[field].strip()
                for field in required_fields
            )
            for item in competitors
        ),
        f"{label} lacks a source or direct comparison",
    )
    check(
        all(set(item) <= allowed_fields for item in competitors),
        f"{label} contains unsupported fields",
    )
    competitor_ids = [item["canonical_id"] for item in competitors]
    check(
        len(competitor_ids) == len(set(competitor_ids)),
        f"{label} contains duplicate records",
    )
    if excluded_id is not None:
        check(excluded_id not in competitor_ids, f"{label} lists its own competitor")
    check(
        all(is_primary_url(item["url"]) for item in competitors),
        f"{label} uses a non-primary URL",
    )
    check(
        all(identity_matches(item) for item in competitors),
        f"{label} has a canonical ID and URL mismatch",
    )
    check(
        all(source_matches(item) for item in competitors),
        f"{label} has a source kind and URL mismatch",
    )
    optional_text_fields = ("checked_at", "source_version", "source_date")
    check(
        all(
            all(
                field not in item
                or (isinstance(item[field], str) and item[field].strip())
                for field in optional_text_fields
            )
            for item in competitors
        ),
        f"{label} has invalid source provenance",
    )
    check(
        all(
            all(
                field not in item or is_iso_date(item[field])
                for field in ("checked_at", "source_date")
            )
            for item in competitors
        ),
        f"{label} has invalid source dates",
    )
    allowed_source_kinds = {
        "arxiv",
        "openreview",
        "official-proceedings",
        "publisher",
    }
    check(
        all(
            "source_kind" not in item or item["source_kind"] in allowed_source_kinds
            for item in competitors
        ),
        f"{label} has an unknown source kind",
    )
    if not require_provenance:
        return

    for item in competitors:
        status = item.get("provenance_status")
        check(
            status in {VERSION_VERIFIED, LEGACY_UNVERSIONED},
            f"{label} has no explicit provenance status: {item['canonical_id']}",
        )
        check(
            item.get("source_kind") in allowed_source_kinds
            and is_iso_date(item.get("checked_at")),
            f"{label} has incomplete provenance: {item['canonical_id']}",
        )
        if status == VERSION_VERIFIED:
            check(
                isinstance(item.get("source_version"), str)
                and bool(item["source_version"].strip())
                and is_iso_date(item.get("source_date"))
                and item["source_date"] <= item["checked_at"],
                f"{label} has an incomplete verified revision: {item['canonical_id']}",
            )
        else:
            check(
                "source_version" not in item and "source_date" not in item,
                f"{label} marks partial provenance as legacy: {item['canonical_id']}",
            )


def validate_schema(validator: Draft202012Validator, value: dict, label: str) -> None:
    """Raise the first JSON-Schema error with a compact, navigable path."""
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise RuntimeError(f"{label} schema violation at {location}: {error.message}")
