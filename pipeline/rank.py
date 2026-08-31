"""Auditable relevance and interest ranking for daily arXiv intake."""

from __future__ import annotations

import json
from pathlib import Path

from ontology import TOPICS, TRICKS, phrase_hit, route


def load_rules(path: Path) -> dict:
    """Load ranking policy separately from executable pipeline code."""
    rules = json.loads(path.read_text(encoding="utf-8"))
    validate_rules(rules)
    return rules


def validate_rules(rules: dict) -> None:
    """Reject incomplete or ambiguous relevance policies before intake starts."""
    required = {
        "version",
        "core_categories",
        "field_categories",
        "selective_prefixes",
        "strong_terms",
        "support_terms",
        "interest_terms",
        "priority_topics",
        "priority_tricks",
        "selective_threshold",
        "adjacent_threshold",
        "shortlist_size",
    }
    missing = required - set(rules)
    if missing:
        raise RuntimeError(
            "Daily feed policy is missing: " + ", ".join(sorted(missing))
        )
    lists = (
        "core_categories",
        "field_categories",
        "selective_prefixes",
        "priority_topics",
        "priority_tricks",
    )
    if not isinstance(rules["version"], str) or not rules["version"].strip():
        raise RuntimeError("Daily feed policy requires a version")
    if any(
        not isinstance(rules[key], list)
        or not rules[key]
        or not all(isinstance(item, str) and item for item in rules[key])
        for key in lists
    ):
        raise RuntimeError("Daily feed policy lists must contain strings")
    if set(rules["core_categories"]) & set(rules["field_categories"]):
        raise RuntimeError("Daily feed category lanes overlap")
    for key in ("strong_terms", "support_terms", "interest_terms"):
        terms = rules[key]
        if (
            not isinstance(terms, dict)
            or not terms
            or not all(
                isinstance(term, str)
                and term
                and isinstance(weight, (int, float))
                and not isinstance(weight, bool)
                and weight > 0
                for term, weight in terms.items()
            )
        ):
            raise RuntimeError(f"Daily feed {key} must map phrases to positive weights")
    if not all(
        isinstance(rules[key], (int, float))
        and not isinstance(rules[key], bool)
        and 0 <= rules[key] <= 10
        for key in ("selective_threshold", "adjacent_threshold")
    ):
        raise RuntimeError("Daily feed thresholds must be between 0 and 10")
    if not isinstance(rules["shortlist_size"], int) or rules["shortlist_size"] < 1:
        raise RuntimeError("Daily feed shortlist size must be a positive integer")


def term_hits(text: str, terms: dict[str, float]) -> list[str]:
    """Find distinct bounded phrases in deterministic configuration order."""
    lowered = text.lower()
    return [
        phrase
        for phrase in terms
        if phrase_hit(lowered, phrase)
    ]


def hit_score(hits: list[str], terms: dict[str, float]) -> float:
    """Sum configured weights for a set of distinct phrase matches."""
    return sum(float(terms[hit]) for hit in hits)


def paper_lane(categories: list[str], rules: dict) -> str:
    """Describe why a category family enters the ML relevance filter."""
    if set(categories) & set(rules["core_categories"]):
        return "core"
    if set(categories) & set(rules["field_categories"]):
        return "field"
    if any(
        category.startswith(tuple(rules["selective_prefixes"]))
        for category in categories
    ):
        return "math-stat"
    return "adjacent"


def relevance_score(paper: dict, rules: dict) -> dict:
    """Score recall-oriented ML relevance and retain interpretable reasons."""
    categories = paper.get("categories", [])
    lane = paper_lane(categories, rules)
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
    title = paper.get("title", "")
    strong = term_hits(text, rules["strong_terms"])
    support = term_hits(text, rules["support_terms"])
    title_hits = set(term_hits(title, rules["strong_terms"]))
    base = {"core": 8.0, "field": 5.0}.get(lane, 0.0)
    phrase_score = hit_score(strong, rules["strong_terms"])
    phrase_score += hit_score(support, rules["support_terms"])
    phrase_score += sum(float(rules["strong_terms"][hit]) * 0.3 for hit in title_hits)
    score = round(min(10.0, base + phrase_score), 1)
    if lane in {"core", "field"}:
        relevant = True
    elif lane == "math-stat":
        relevant = bool(strong) and score >= float(rules["selective_threshold"])
    else:
        relevant = bool(strong) and score >= float(rules["adjacent_threshold"])

    reasons = []
    if lane == "core":
        reasons.append("core ML category")
    elif lane == "field":
        reasons.append("ML-intensive field category")
    if strong:
        reasons.append("strong signals: " + ", ".join(strong[:4]))
    if support:
        reasons.append("supporting signals: " + ", ".join(support[:3]))
    return {
        "relevant": relevant,
        "score": score,
        "lane": lane,
        "reasons": reasons,
        "strong_hits": strong,
        "support_hits": support,
    }


def interest_score(paper: dict, relevance: dict, rules: dict) -> dict:
    """Rank triage value without changing the relevance retention boundary."""
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
    topics = route(text, TOPICS, limit=6)
    tricks = route(text, TRICKS, limit=6)
    hits = term_hits(text, rules["interest_terms"])
    score = relevance["score"] * 0.45
    score += hit_score(hits, rules["interest_terms"])
    topic_ids = {item["id"] for item in topics}
    trick_ids = {item["id"] for item in tricks}
    topic_bonus = topic_ids & set(rules["priority_topics"])
    trick_bonus = trick_ids & set(rules["priority_tricks"])
    score += min(1.5, len(topic_bonus) * 0.35)
    score += min(1.5, len(trick_bonus) * 0.4)
    if len(paper.get("categories", [])) > 1:
        score += 0.2
    reasons = []
    if hits:
        reasons.append("interest signals: " + ", ".join(hits[:4]))
    if topic_bonus:
        reasons.append("priority topics: " + ", ".join(sorted(topic_bonus)))
    if trick_bonus:
        reasons.append("priority methods: " + ", ".join(sorted(trick_bonus)))
    return {
        "score": round(min(10.0, score), 1),
        "reasons": reasons,
        "topics": topics,
        "tricks": tricks,
    }


def rank_paper(paper: dict, rules: dict) -> dict:
    """Attach independent relevance and interest assessments to one paper."""
    relevance = relevance_score(paper, rules)
    interest = interest_score(paper, relevance, rules)
    return {
        **paper,
        "relevance": relevance,
        "interest": interest,
        "topics": interest.pop("topics"),
        "tricks": interest.pop("tricks"),
    }


def rank_day(papers: list[dict], rules: dict) -> list[dict]:
    """Return every relevance-positive paper in stable triage order."""
    ranked = [rank_paper(paper, rules) for paper in papers]
    relevant = [paper for paper in ranked if paper["relevance"]["relevant"]]
    return sorted(
        relevant,
        key=lambda paper: (
            -paper["interest"]["score"],
            -paper["relevance"]["score"],
            paper["title"].casefold(),
            paper["id"],
        ),
    )
