#!/usr/bin/env python3
"""Build stable second-review assignments for every canonical paper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assign import canonical_papers
from ledger import load_readings
from paths import REVIEWED_READINGS_DIR
from files import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
PAPERS_PATH = ROOT / "data/generated/papers_enriched.json"
OUTPUT_PATH = ROOT / "data/generated/verification_queue.json"

REVIEWABLE_STATES = {"needs-structural-upgrade", "needs-second-review"}


def review_reasons(reading: dict) -> list[str]:
    """Return concrete reasons that keep a reading outside verified state."""
    reasons = []
    if any(not finding.get("attribution") for finding in reading["key_findings"]):
        reasons.append("missing-finding-attribution")
    if not isinstance(reading.get("novelty_assessment"), dict):
        reasons.append("unstructured-novelty")
    if len(reading.get("competitive_landscape", [])) < 5:
        reasons.append("thin-competitor-panel")
    if reading.get("reading_depth") != "verified":
        reasons.append("second-review-lineage-missing")
    return reasons


def review_state(reading: dict | None) -> tuple[str, list[str]]:
    """Classify one paper for a reviewer without conflating unread and verified."""
    if reading is None:
        return "unread", ["full-reading-missing"]
    reasons = review_reasons(reading)
    structural = {"missing-finding-attribution", "unstructured-novelty"}
    if structural.intersection(reasons):
        return "needs-structural-upgrade", reasons
    if reasons:
        return "needs-second-review", reasons
    return "verified", []


def assignment_status(papers: list[dict]) -> str:
    """Summarize whether a fixed batch contains actionable reviewer work."""
    states = [paper["review_state"] for paper in papers]
    if all(state == "verified" for state in states):
        return "complete"
    if not any(state in REVIEWABLE_STATES for state in states):
        return "awaiting-reading"
    if any(state == "unread" for state in states):
        return "partially-ready"
    return "ready"


def build_verification_queue(
    records: list[dict], readings: dict[str, dict], *, batch_size: int
) -> dict:
    """Return fixed canonical batches with explicit second-review states."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    papers = []
    for record in canonical_papers(records):
        stable_id = record["stable_id"]
        state, reasons = review_state(readings.get(stable_id))
        papers.append(
            {
                "stable_id": stable_id,
                "title": record["title"],
                "review_state": state,
                "review_reasons": reasons,
            }
        )

    assignments = []
    for start in range(0, len(papers), batch_size):
        batch = papers[start : start + batch_size]
        assignments.append(
            {
                "id": f"corpus-verification-{start // batch_size + 1:04d}",
                "status": assignment_status(batch),
                "papers": batch,
            }
        )

    state_names = (
        "unread",
        "needs-structural-upgrade",
        "needs-second-review",
        "verified",
    )
    status_names = ("complete", "ready", "partially-ready", "awaiting-reading")
    return {
        "batch_size": batch_size,
        "canonical_paper_count": len(papers),
        "assignment_count": len(assignments),
        "paper_states": {
            state: sum(paper["review_state"] == state for paper in papers)
            for state in state_names
        },
        "assignment_states": {
            status: sum(assignment["status"] == status for assignment in assignments)
            for status in status_names
        },
        "assignments": assignments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    records = json.loads(PAPERS_PATH.read_text(encoding="utf-8"))
    queue = build_verification_queue(
        records,
        load_readings(REVIEWED_READINGS_DIR),
        batch_size=args.batch_size,
    )
    atomic_write_text(
        args.output,
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
    )
    print(
        f"Wrote {queue['assignment_count']} fixed verification assignments; "
        f"{queue['assignment_states']['ready']} are ready"
    )


if __name__ == "__main__":
    main()
