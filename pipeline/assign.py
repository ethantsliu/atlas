#!/usr/bin/env python3
"""Partition the canonical corpus into stable, non-overlapping review assignments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ledger import load_json_lines, load_readings
from paths import REVIEWED_READINGS_DIR
from files import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
PAPERS_PATH = ROOT / "data/generated/papers_enriched.json"
FULLTEXT_PATH = ROOT / "data/generated/fulltext_index.jsonl"
OUTPUT_PATH = ROOT / "data/generated/reading_queue.json"


def canonical_papers(records: list[dict]) -> list[dict]:
    """Keep one ordered record per paper identity and omit contextual entries."""
    unique: dict[str, dict] = {}
    for record in records:
        if record.get("record_kind") == "non_paper_context":
            continue
        unique.setdefault(record["stable_id"], record)
    return list(unique.values())


def assignment_status(papers: list[dict]) -> str:
    """Summarize whether a fixed assignment can be handed to a reading agent."""
    unfinished = [paper for paper in papers if paper["state"] != "reviewed"]
    if not unfinished:
        return "complete"
    ready = [paper for paper in unfinished if paper["state"] == "ready"]
    if len(ready) == len(unfinished):
        return "ready"
    if ready:
        return "partially-ready"
    return "awaiting-extraction"


def build_reading_queue(
    records: list[dict],
    fulltext_entries: list[dict],
    reviewed_ids: set[str],
    *,
    batch_size: int,
) -> dict:
    """Return stable corpus batches whose ordinal IDs never shift between runs."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    extraction_status = {
        entry["stable_id"]: entry.get("status") for entry in fulltext_entries
    }
    papers = []
    for record in canonical_papers(records):
        stable_id = record["stable_id"]
        state = (
            "reviewed"
            if stable_id in reviewed_ids
            else "ready"
            if extraction_status.get(stable_id) == "full_text_ok"
            else "awaiting-extraction"
        )
        papers.append(
            {
                "stable_id": stable_id,
                "title": record["title"],
                "state": state,
                "extraction_status": extraction_status.get(stable_id, "pending"),
            }
        )

    assignments = []
    for start in range(0, len(papers), batch_size):
        batch = papers[start : start + batch_size]
        assignments.append(
            {
                "id": f"corpus-reading-{start // batch_size + 1:04d}",
                "status": assignment_status(batch),
                "papers": batch,
            }
        )

    state_counts = {
        state: sum(paper["state"] == state for paper in papers)
        for state in ("reviewed", "ready", "awaiting-extraction")
    }
    assignment_counts = {
        status: sum(assignment["status"] == status for assignment in assignments)
        for status in ("complete", "ready", "partially-ready", "awaiting-extraction")
    }
    return {
        "batch_size": batch_size,
        "canonical_paper_count": len(papers),
        "assignment_count": len(assignments),
        "paper_states": state_counts,
        "assignment_states": assignment_counts,
        "assignments": assignments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    records = json.loads(PAPERS_PATH.read_text(encoding="utf-8"))
    fulltext_entries = load_json_lines(FULLTEXT_PATH)
    reviewed_ids = set(load_readings(REVIEWED_READINGS_DIR))
    queue = build_reading_queue(
        records,
        fulltext_entries,
        reviewed_ids,
        batch_size=args.batch_size,
    )
    atomic_write_text(
        args.output,
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
    )
    print(
        f"Wrote {queue['assignment_count']} fixed assignments; "
        f"{queue['assignment_states']['ready']} are ready"
    )


if __name__ == "__main__":
    main()
