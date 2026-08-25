"""Pure helpers for routing and summarizing paper records."""

from __future__ import annotations

import re

from ontology import TOPICS, TRICKS, route
from assets import reading_public_path


def split_sentences(text: str) -> list[str]:
    """Split abstract prose without treating short fragments as sentences."""
    pattern = r"(?<=[.!?])\s+(?=[A-Z0-9])"
    return [part.strip() for part in re.split(pattern, text) if len(part.strip()) > 30]


def first_matching(sentences: list[str], terms: tuple[str, ...], fallback: str) -> str:
    """Return the first sentence containing any search term."""
    return next(
        (
            sentence
            for sentence in sentences
            if any(term in sentence.lower() for term in terms)
        ),
        fallback,
    )


def summarize_abstract(record: dict) -> dict:
    """Create a transparent extractive preview from an abstract.

    This is intentionally not called a full-paper summary. The caller must retain
    the record's reading-depth label.
    """
    abstract = record.get("abstract") or ""
    sentences = split_sentences(abstract)
    if not sentences:
        return {
            "problem": "A full reading has not yet been completed.",
            "approach": (
                "The collection currently provides only title-level evidence "
                "for this record."
            ),
            "evidence": "No abstract or result passage is available locally.",
            "limitations": (
                "Do not use this provisional record as evidence until the "
                "source is read."
            ),
            "why_it_matters": "Queued for structured reading.",
        }

    problem = sentences[0]
    approach = first_matching(
        sentences[1:],
        (
            "we propose",
            "we introduce",
            "we present",
            "we develop",
            "our method",
            "we study",
        ),
        sentences[min(1, len(sentences) - 1)],
    )
    evidence = first_matching(
        sentences,
        ("result", "outperform", "achieve", "improve", "show that", "demonstrate"),
        "The abstract does not state a quantitative result.",
    )
    limitation = first_matching(
        sentences,
        ("limitation", "however", "remain", "challenge"),
        "The abstract does not report limitations; verify them in the full paper.",
    )
    return {
        "problem": problem,
        "approach": approach,
        "evidence": evidence,
        "limitations": limitation,
        "why_it_matters": first_matching(
            sentences,
            ("enable", "important", "practical", "benefit"),
            problem,
        ),
    }


def summarize_context_record(record: dict) -> dict:
    """Describe why a non-paper collection entry is retained without inventing claims."""
    return {
        "problem": "This is a contextual collection entry, not a paper.",
        "approach": (
            "The atlas preserves the original link as curator context while excluding "
            "it from paper-reading and related-work requirements."
        ),
        "evidence": record.get("note")
        or "No abstract, experiment, or paper-level claim is attached to this entry.",
        "limitations": (
            "Do not cite this record as research evidence; inspect the linked resource "
            "for its own provenance and scope."
        ),
        "why_it_matters": "It may explain the curator's interests or point to supporting material.",
    }


def compact_paper(record: dict, full_reading: dict | None = None) -> dict:
    """Build the compact paper record consumed by the web application."""
    record_kind = record.get("record_kind", "paper")
    is_context = record_kind == "non_paper_context"
    evidence_text = " ".join(
        str(value or "")
        for value in (
            record.get("title"),
            record.get("abstract"),
            record.get("note"),
            " ".join(record.get("tags", [])),
        )
    )
    reading_depth = (
        "context"
        if is_context
        else full_reading.get("reading_depth", "full_text")
        if full_reading
        else record.get("reading_depth", "metadata")
    )
    paper = {
        "id": f"paper-{record['id']}",
        "stable_id": record.get("stable_id"),
        "collection_id": record["id"],
        "record_kind": record_kind,
        "title": record.get("title"),
        "url": record.get("resolved_url") or record.get("url"),
        "collection_url": record.get("url"),
        "source": record.get("source"),
        "authors": record.get("authors", []),
        "published": record.get("published"),
        "categories": record.get("categories", []),
        "note": record.get("note"),
        "reading_depth": reading_depth,
        "topics": route(evidence_text, TOPICS),
        "tricks": route(evidence_text, TRICKS),
        "reading": summarize_context_record(record)
        if is_context
        else summarize_abstract(record),
    }
    if full_reading and not is_context and reading_depth in {"full_text", "verified"}:
        paper["full_reading_path"] = reading_public_path(
            record["stable_id"], full_reading
        )
    return paper
