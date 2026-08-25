"""Load and merge audited provenance for idea-level competitor records.

The research brief is deliberately kept readable: comparison prose stays beside
the idea, while revision metadata that is shared across ideas lives in one
canonical-ID keyed sidecar.  A record is either fully version verified or
explicitly legacy/unversioned; missing metadata is never silently promoted.
"""

from __future__ import annotations

import json
import html
import re
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from rules import LEGACY_UNVERSIONED, VERSION_VERIFIED, check, is_iso_date

PROVENANCE_SCHEMA_VERSION = "competitor-provenance-v1"
PROVENANCE_STATUSES = {VERSION_VERIFIED, LEGACY_UNVERSIONED}
SOURCE_KINDS = {"arxiv", "openreview", "official-proceedings", "publisher"}
PUBLIC_PROVENANCE_FIELDS = (
    "provenance_status",
    "source_kind",
    "source_version",
    "source_date",
    "checked_at",
)
SIDECAR_RECORD_FIELDS = {
    *PUBLIC_PROVENANCE_FIELDS,
    "source_locator",
    "verified_title",
    "unresolved_reason",
}


def normalized_title(value: str) -> str:
    """Normalize harmless archive typography without erasing word differences."""
    value = html.unescape(value)
    value = re.sub(r"\\([{}_$%&#])", r"\1", value)
    value = re.sub(r"[{}]", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return " ".join(value.split())


def titles_match(left: str, right: str) -> bool:
    """Allow minor TeX/punctuation drift while rejecting a wrong source record."""
    left_normalized = normalized_title(left)
    right_normalized = normalized_title(right)
    return (
        left_normalized == right_normalized
        or SequenceMatcher(None, left_normalized, right_normalized).ratio() >= 0.92
    )


def validate_provenance_record(canonical_id: str, record: object) -> None:
    """Validate one sidecar row without weakening unresolved records."""
    label = f"Competitor provenance {canonical_id}"
    check(isinstance(record, dict), f"{label} is not an object")
    check(
        not (set(record) - SIDECAR_RECORD_FIELDS),
        f"{label} contains unknown fields: {sorted(set(record) - SIDECAR_RECORD_FIELDS)}",
    )
    status = record.get("provenance_status")
    check(status in PROVENANCE_STATUSES, f"{label} has an unknown status")
    check(record.get("source_kind") in SOURCE_KINDS, f"{label} has no source kind")
    for field in ("source_locator", "verified_title"):
        check(
            isinstance(record.get(field), str) and bool(record[field].strip()),
            f"{label} has invalid {field}",
        )
    locator = urlparse(record["source_locator"])
    check(
        locator.scheme == "https" and bool(locator.hostname),
        f"{label} has a non-HTTPS source locator",
    )
    check(is_iso_date(record.get("checked_at")), f"{label} has invalid checked_at")

    if status == VERSION_VERIFIED:
        check(
            isinstance(record.get("source_version"), str)
            and bool(record["source_version"].strip()),
            f"{label} is verified without an exact source version",
        )
        check(
            is_iso_date(record.get("source_date")),
            f"{label} is verified without an exact source date",
        )
        check(
            record["source_date"] <= record["checked_at"],
            f"{label} has a source date after its check date",
        )
        check(
            "unresolved_reason" not in record,
            f"{label} is both verified and unresolved",
        )
        return

    check(
        isinstance(record.get("unresolved_reason"), str)
        and bool(record["unresolved_reason"].strip()),
        f"{label} needs an unresolved reason",
    )
    check(
        "source_version" not in record and "source_date" not in record,
        f"{label} has partial version metadata but is marked legacy",
    )


def validate_provenance_payload(payload: object) -> dict[str, dict]:
    """Return validated records from the versioned sidecar envelope."""
    check(isinstance(payload, dict), "Competitor provenance payload is not an object")
    check(
        set(payload) == {"schema_version", "records"},
        "Competitor provenance payload has an unexpected shape",
    )
    check(
        payload.get("schema_version") == PROVENANCE_SCHEMA_VERSION,
        "Competitor provenance schema version is unsupported",
    )
    records = payload.get("records")
    check(isinstance(records, dict), "Competitor provenance records are not an object")
    for canonical_id, record in records.items():
        check(
            isinstance(canonical_id, str) and bool(canonical_id.strip()),
            "Competitor provenance has an invalid canonical ID",
        )
        validate_provenance_record(canonical_id, record)
    return records


def load_competitors(path: Path) -> dict[str, dict]:
    """Read the audited sidecar and fail clearly when it is unavailable."""
    if not path.is_file():
        raise RuntimeError(f"Missing competitor provenance sidecar: {path}")
    return validate_provenance_payload(json.loads(path.read_text(encoding="utf-8")))


def competitor_ids(ideas: list[dict]) -> set[str]:
    """Collect canonical IDs only from idea-level reviewed landscapes."""
    return {
        competitor["canonical_id"]
        for idea in ideas
        for competitor in idea.get("brief", {}).get("competitive_landscape", [])
    }


def merge_competitors(ideas: list[dict], records: dict[str, dict]) -> list[dict]:
    """Return a deep-copied brief collection with exact public provenance merged."""
    expected_ids = competitor_ids(ideas)
    actual_ids = set(records)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    check(not missing, f"Competitor provenance is missing IDs: {', '.join(missing)}")
    check(not extra, f"Competitor provenance has stale IDs: {', '.join(extra)}")

    merged_ideas = deepcopy(ideas)
    for idea in merged_ideas:
        competitors = idea.get("brief", {}).get("competitive_landscape", [])
        for competitor in competitors:
            record = records[competitor["canonical_id"]]
            check(
                titles_match(competitor["title"], record["verified_title"]),
                f"Competitor title conflicts with primary metadata for "
                f"{competitor['canonical_id']}",
            )
            for field in PUBLIC_PROVENANCE_FIELDS:
                if field not in record:
                    continue
                existing = competitor.get(field)
                check(
                    existing is None or existing == record[field],
                    f"Inline provenance conflicts with sidecar for "
                    f"{competitor['canonical_id']}: {field}",
                )
                competitor[field] = record[field]
    return merged_ideas


def load_flagships(path: Path, provenance_path: Path) -> list[dict]:
    """Load human-readable ideas and their canonical provenance as one view."""
    ideas = json.loads(path.read_text(encoding="utf-8"))
    check(isinstance(ideas, list), "Flagship ideas source is not a list")
    records = load_competitors(provenance_path)
    return merge_competitors(ideas, records)
