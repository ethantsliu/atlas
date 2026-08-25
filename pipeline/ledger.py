"""Coverage accounting shared by the pipeline and completion ledger.

The module name deliberately avoids ``coverage`` so local imports cannot shadow
the third-party package used by test runners.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from files import atomic_write_text

PUBLIC_EXTRACTION_ISSUE_FIELDS = (
    "stable_id",
    "status",
    "source_route",
    "pages_with_text",
    "page_count",
    "missing_text_pages",
    "text_coverage_ratio",
    "error_type",
)


class DuplicateKeyError(ValueError):
    """Identify an ambiguous JSON object before ordinary parsing can overwrite it."""


def reject_keys(pairs: list[tuple[str, object]]) -> dict:
    """Build one JSON object while rejecting repeated member names."""
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def parse_json(payload: str, label: str) -> object:
    """Parse JSON with duplicate-member rejection and a source-aware error."""
    try:
        return json.loads(payload, object_pairs_hook=reject_keys)
    except DuplicateKeyError as error:
        raise RuntimeError(f"Duplicate JSON object key in {label}: {error}") from error


def load_json(path: Path) -> object:
    """Load one strict JSON document."""
    return parse_json(path.read_text(encoding="utf-8"), str(path))


def load_json_lines(path: Path) -> list[dict]:
    """Load strict JSONL, returning an empty list when it does not exist."""
    if not path.exists():
        return []
    return [
        parse_json(line, f"{path}:{number}")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip()
    ]


def validate_json(*roots: Path) -> None:
    """Strictly parse every JSON validation input below the supplied roots."""
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix == ".json":
                load_json(path)
            elif path.suffix == ".jsonl":
                load_json_lines(path)


def load_readings(directory: Path) -> dict[str, dict]:
    """Index structured full-paper readings by canonical paper ID."""
    readings: dict[str, dict] = {}
    if not directory.exists():
        return readings
    for path in sorted(directory.glob("*.json")):
        reading = load_json(path)
        readings[reading["stable_id"]] = reading
    return readings


def write_coverage_snapshot(path: Path, snapshot: dict) -> None:
    """Persist the exact snapshot embedded in the atlas."""
    atomic_write_text(path, json.dumps(snapshot, indent=2) + "\n")


def public_extraction_issue(entry: dict) -> dict:
    """Project one incomplete extraction without paths, URLs, hashes, or raw errors."""
    return {
        field: entry[field]
        for field in PUBLIC_EXTRACTION_ISSUE_FIELDS
        if field in entry
    }


def build_coverage_snapshot(
    papers: list[dict],
    fulltext_entries: list[dict],
    readings: dict[str, dict],
    source_inventory: dict | None = None,
    updated_at: str | None = None,
) -> dict:
    """Build a transparent snapshot for progress reporting and the UI."""
    canonical_ids = {paper["stable_id"] for paper in papers}
    inventory_records = (source_inventory or {}).get("records", [])
    canonical_paper_ids = (
        {
            row["stable_id"]
            for row in inventory_records
            if row.get("requires_reading", True)
        }
        if inventory_records
        else canonical_ids
    )
    extracted_ids = {
        entry["stable_id"]
        for entry in fulltext_entries
        if entry.get("status") == "full_text_ok"
        and entry["stable_id"] in canonical_paper_ids
    }
    extraction_failures = [
        public_extraction_issue(entry)
        for entry in fulltext_entries
        if entry["stable_id"] in canonical_ids and entry.get("status") != "full_text_ok"
    ]

    entry_depths = Counter()
    for paper in papers:
        if paper.get("record_kind") == "non_paper_context":
            entry_depths["context"] += 1
        elif paper["stable_id"] in readings:
            entry_depths[
                readings[paper["stable_id"]].get("reading_depth", "full_text")
            ] += 1
        elif paper.get("abstract"):
            entry_depths["abstract"] += 1
        else:
            entry_depths["metadata"] += 1

    competitive_count = sum(
        bool(reading.get("competitive_landscape")) for reading in readings.values()
    )
    canonical_total = len(canonical_ids)
    source_summary = (source_inventory or {}).get(
        "summary",
        {
            "canonical_records_classified": 0,
            "paper_records": canonical_total,
            "non_paper_records": 0,
            "adapter_supported": 0,
            "adapter_missing": canonical_total,
            "by_route": {},
            "by_extraction_status": {},
        },
    )
    supported_ids = {
        row["stable_id"]
        for row in (source_inventory or {}).get("records", [])
        if row.get("requires_reading", True) and row.get("adapter_supported")
    }
    remaining_supported = len(supported_ids - set(readings))
    completion_satisfied = (
        source_summary["canonical_records_classified"] == canonical_total
        and source_summary["adapter_missing"] == 0
        and remaining_supported == 0
    )
    return {
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
        "collection_entries": len(papers),
        "canonical_records": canonical_total,
        "entry_reading_depth": dict(sorted(entry_depths.items())),
        "abstract_entries": sum(bool(paper.get("abstract")) for paper in papers),
        "fulltext_extracted": len(extracted_ids),
        "full_readings": len(readings),
        "competitive_landscapes": competitive_count,
        "canonical_paper_fulltext_extraction_coverage": round(
            len(extracted_ids) / max(1, len(canonical_paper_ids)), 4
        ),
        "canonical_paper_full_reading_coverage": round(
            len(set(readings) & canonical_paper_ids) / max(1, len(canonical_paper_ids)),
            4,
        ),
        "extraction_failures": extraction_failures,
        "source_access": {
            **source_summary,
            "supported_records_without_readings": remaining_supported,
        },
        "completion_gate": {
            "satisfied": completion_satisfied,
            "rule": (
                "Every canonical record must be classified; every retrievable "
                "paper needs a page-anchored reading and competitive landscape."
            ),
        },
    }
