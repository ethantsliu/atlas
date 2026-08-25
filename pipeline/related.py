#!/usr/bin/env python3
"""Build an auditable arXiv candidate queue for later competitive-landscape review."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

from ledger import load_readings
from paths import REVIEWED_READINGS_DIR
from files import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "data/generated/papers_enriched.json"
OUTPUT = ROOT / "data/generated/related_work_candidates.jsonl"
READINGS_DIR = REVIEWED_READINGS_DIR
TOKEN = re.compile(r"[a-z][a-z0-9-]{2,}")
STOP = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "are",
    "our",
    "have",
    "has",
    "using",
    "use",
    "into",
    "their",
    "which",
    "can",
    "model",
    "models",
    "learning",
    "paper",
    "method",
    "methods",
    "based",
    "new",
    "show",
    "results",
    "approach",
    "data",
    "task",
    "tasks",
    "performance",
    "training",
    "propose",
    "proposed",
    "large",
    "neural",
}


def terms(record: dict) -> Counter[str]:
    title = (record.get("title") or "").lower()
    abstract = (record.get("abstract") or "").lower()
    values = [
        term
        for term in TOKEN.findall(f"{title} {title} {title} {abstract}")
        if term not in STOP
    ]
    return Counter(values)


def build_work_rows(records: list[dict], readings: dict[str, dict]) -> list[dict]:
    """Deterministically derive lexical queues and reviewed evidence rows."""
    vectors = [
        Counter() if record.get("record_kind") == "non_paper_context" else terms(record)
        for record in records
    ]
    postings: dict[str, list[int]] = defaultdict(list)
    for index, vector in enumerate(vectors):
        for term in vector:
            postings[term].append(index)
    count = sum(bool(vector) for vector in vectors)
    idf = {
        term: math.log((count + 1) / (len(indices) + 1))
        for term, indices in postings.items()
    }
    rows = []
    for index, (record, vector) in enumerate(zip(records, vectors)):
        if record.get("record_kind") == "non_paper_context":
            rows.append(
                {
                    "stable_id": record.get("stable_id"),
                    "collection_id": record["id"],
                    "title": record.get("title"),
                    "candidates": [],
                    "review_status": "not_applicable",
                    "reviewed_competitors": [],
                    "warning": "Contextual collection entry; no paper-level related-work claim is applicable.",
                }
            )
            continue
        scores: dict[int, float] = defaultdict(float)
        shared: dict[int, list[tuple[float, str]]] = defaultdict(list)
        rare = sorted(vector, key=lambda term: (-idf[term], term))[:35]
        for term in rare:
            weight = idf[term] * min(3, vector[term])
            for candidate in postings[term]:
                if candidate == index or records[candidate].get(
                    "stable_id"
                ) == record.get("stable_id"):
                    continue
                scores[candidate] += weight
                shared[candidate].append((weight, term))
        source_categories = set(record.get("categories", []))
        for candidate in list(scores):
            overlap = source_categories & set(records[candidate].get("categories", []))
            scores[candidate] += 0.7 * len(overlap)
        ranked = sorted(scores, key=lambda candidate: (-scores[candidate], candidate))[
            :12
        ]
        candidates = []
        for candidate in ranked:
            item = records[candidate]
            candidates.append(
                {
                    "stable_id": item.get("stable_id"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "similarity_score": round(scores[candidate], 3),
                    "shared_terms": [
                        term for _, term in sorted(shared[candidate], reverse=True)[:6]
                    ],
                    "status": "candidate_only",
                }
            )
        reviewed = readings.get(record.get("stable_id"))
        rows.append(
            {
                "stable_id": record.get("stable_id"),
                "collection_id": record["id"],
                "title": record.get("title"),
                "candidates": candidates,
                "review_status": "reviewed" if reviewed else "unreviewed",
                "reviewed_competitors": (
                    deepcopy(reviewed.get("competitive_landscape", []))
                    if reviewed
                    else []
                ),
                "warning": "Lexical candidates are a research queue, not a claim of competition or novelty.",
            }
        )
    return rows


def main() -> None:
    records = json.loads(PAPERS.read_text(encoding="utf-8"))
    readings = load_readings(READINGS_DIR)
    rows = build_work_rows(records, readings)
    atomic_write_text(
        OUTPUT,
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    print(
        f"Built related-work candidate queues for {len(rows)} collection entries -> {OUTPUT}"
    )


if __name__ == "__main__":
    main()
