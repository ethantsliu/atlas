"""Build the bounded semantic text attached to each Atlas node."""

from __future__ import annotations

import json
from pathlib import Path

from ontology import TOPICS, TRICKS


ROOT = Path(__file__).resolve().parents[1]
DETAILS_PATH = ROOT / "data/reviewed/readings"
PLACEHOLDERS = (
    "full reading has not yet been completed",
    "collection currently provides only title-level evidence",
    "no abstract or result passage is available locally",
)


def route_names(item: dict) -> str:
    routes = [*item.get("topics", []), *item.get("tricks", [])]
    return ", ".join(route.get("id", "") for route in routes)


def clip_words(value: object, limit: int) -> str:
    """Clip normalized prose at a word boundary within a field budget."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    clipped = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return clipped or text[:limit]


def detail_text(detail: dict) -> str:
    """Budget every reviewed field so later semantic signals survive."""
    method = detail.get("method", {})
    techniques = ", ".join(
        str(item.get("id", "")) for item in detail.get("techniques", [])[:6]
    )
    return " ".join(
        part
        for part in (
            f"question: {clip_words(detail.get('question'), 100)}",
            f"core idea: {clip_words(method.get('core_idea'), 170)}",
            f"mechanism: {clip_words(method.get('mechanism'), 170)}",
            f"techniques: {clip_words(techniques, 70)}",
        )
        if part.split(": ", 1)[-1]
    )


def paper_text(paper: dict, detail: dict | None = None) -> str:
    reading = paper.get("reading", {})
    reviewed = detail_text(detail) if detail else ""
    compact = " ".join(str(reading.get(key, "")) for key in ("problem", "approach"))
    if any(phrase in compact.casefold() for phrase in PLACEHOLDERS):
        compact = ""
    prefix = (
        "collection entry"
        if paper.get("record_kind") == "non_paper_context"
        else "research paper"
    )
    return " ".join(
        part
        for part in (
            f"{prefix}: {clip_words(paper['title'], 160)}",
            reviewed or compact,
            f"areas: {clip_words(route_names(paper), 70)}",
        )
        if part.split(": ", 1)[-1]
    )


def idea_text(idea: dict) -> str:
    brief = idea.get("brief", {})
    methods = " ".join(str(item) for item in brief.get("method", [])[:2])
    routes = ", ".join([*idea.get("topic_ids", []), *idea.get("trick_ids", [])])
    return " ".join(
        part
        for part in (
            f"research idea: {clip_words(brief.get('title'), 180)}",
            f"thesis: {clip_words(brief.get('thesis'), 250)}",
            f"proposed method: {clip_words(methods, 250)}",
            f"areas: {clip_words(routes, 80)}",
        )
        if part.split(": ", 1)[-1]
    )


def taxon_text(item: dict) -> str:
    """Describe a taxonomy marker with the same phrases used for paper routing."""
    phrases = TOPICS.get(item["id"], TRICKS.get(item["id"], []))
    if not phrases:
        return item["label"]
    return f"{item['label']}: {', '.join(phrases)}"


def node_records(
    atlas: dict,
    details: dict[str, dict] | None = None,
) -> list[tuple[str, str]]:
    topics = [(f"topic:{item['id']}", taxon_text(item)) for item in atlas["topics"]]
    tricks = [(f"trick:{item['id']}", taxon_text(item)) for item in atlas["tricks"]]
    details = details or {}
    papers = [
        (item["id"], paper_text(item, details.get(item.get("stable_id", ""))))
        for item in atlas["papers"]
    ]
    ideas = [(item["id"], idea_text(item)) for item in atlas["ideas"]]
    return [*topics, *tricks, *papers, *ideas]


def load_details() -> dict[str, dict]:
    """Load authoritative reviewed semantic inputs keyed by canonical paper ID."""
    details: dict[str, dict] = {}
    for path in sorted(DETAILS_PATH.glob("*.json")):
        detail = json.loads(path.read_text(encoding="utf-8"))
        stable_id = detail.get("stable_id")
        if stable_id:
            details[stable_id] = detail
    return details
