"""Pure helpers for creating provisional ideas and feasibility scores."""

from __future__ import annotations

import re
from collections import defaultdict

from experiments import confound_for, protocol_for

FEASIBILITY_FACTOR_MAXIMA = {
    "implementation_leverage": 2.5,
    "compute_and_data": 2.5,
    "evaluation_clarity": 2.0,
    "novelty_risk": 1.5,
    "time_to_signal": 1.5,
}
PROVISIONAL_FACTOR_CAPS = {"evaluation_clarity": 0.9, "novelty_risk": 0.3}
IDEA_ORIGINS = {
    "cross-paper",
    "cross-paper-reviewed",
    "user-specified",
}
BRIEF_STATUSES = {"provisional", "researched-draft"}
ID_CHARS = re.compile(r"[^a-z0-9]+")
LEGACY_IDS = {
    ("efficiency-systems", "retrieval-and-memory"): "idea-standalone-1",
    ("efficiency-systems", "sparsity"): "idea-standalone-2",
    ("evaluation", "retrieval-and-memory"): "idea-standalone-3",
    ("optimization", "regularization"): "idea-standalone-4",
    ("multimodal", "retrieval-and-memory"): "idea-standalone-5",
    ("representation-learning", "sparsity"): "idea-standalone-6",
    ("agents", "retrieval-and-memory"): "idea-standalone-7",
    ("optimization", "sparsity"): "idea-standalone-8",
    ("evaluation", "sparsity"): "idea-standalone-9",
    ("optimization", "retrieval-and-memory"): "idea-standalone-10",
    ("representation-learning", "retrieval-and-memory"): "idea-standalone-11",
    ("reasoning", "retrieval-and-memory"): "idea-standalone-12",
    ("multimodal", "sparsity"): "idea-standalone-13",
    ("interpretability", "sparsity"): "idea-standalone-14",
    ("efficiency-systems", "test-time-compute"): "idea-standalone-15",
    ("reasoning", "sparsity"): "idea-standalone-16",
    ("efficiency-systems", "low-rank-adaptation"): "idea-standalone-17",
    ("representation-learning", "contrastive-learning"): "idea-standalone-18",
    ("evaluation", "routing-and-moe"): "idea-standalone-19",
    ("post-training", "retrieval-and-memory"): "idea-standalone-20",
    ("efficiency-systems", "routing-and-moe"): "idea-standalone-21",
    ("optimization", "normalization"): "idea-standalone-22",
    ("post-training", "sparsity"): "idea-standalone-23",
    ("pre-training", "retrieval-and-memory"): "idea-standalone-24",
    ("evaluation", "test-time-compute"): "idea-standalone-25",
    ("pre-training", "scaling-laws"): "idea-standalone-26",
    ("interpretability", "routing-and-moe"): "idea-standalone-27",
    ("representation-learning", "regularization"): "idea-standalone-28",
    ("efficiency-systems", "regularization"): "idea-standalone-29",
    ("evaluation", "ensembling"): "idea-standalone-30",
    ("efficiency-systems", "distillation"): "idea-standalone-31",
    ("post-training", "low-rank-adaptation"): "idea-standalone-32",
    ("reasoning", "test-time-compute"): "idea-standalone-33",
    ("efficiency-systems", "ensembling"): "idea-standalone-34",
    ("evaluation", "low-rank-adaptation"): "idea-standalone-35",
    ("representation-learning", "routing-and-moe"): "idea-standalone-36",
    ("generative-modeling", "sparsity"): "idea-standalone-37",
    ("optimization", "low-rank-adaptation"): "idea-standalone-38",
    ("reasoning", "routing-and-moe"): "idea-standalone-39",
    ("generative-modeling", "retrieval-and-memory"): "idea-standalone-40",
    ("multimodal", "routing-and-moe"): "idea-standalone-41",
    ("agents", "routing-and-moe"): "idea-standalone-42",
    ("agents", "sparsity"): "idea-standalone-43",
    ("ai-for-science", "sparsity"): "idea-standalone-44",
    ("multimodal", "low-rank-adaptation"): "idea-standalone-45",
    ("evaluation", "regularization"): "idea-standalone-46",
    ("interpretability", "retrieval-and-memory"): "idea-standalone-47",
    ("representation-learning", "ensembling"): "idea-standalone-48",
}


def route_id(value: object) -> str:
    """Normalize one ontology identifier for stable derived IDs."""
    normalized = ID_CHARS.sub("-", str(value or "").casefold()).strip("-")
    if not normalized:
        raise ValueError("Idea routes require non-empty identifiers")
    return normalized


def idea_id(topic: str, trick: str) -> str:
    """Return a rank-independent public ID for one normalized route pair."""
    pair = (route_id(topic), route_id(trick))
    return LEGACY_IDS.get(pair, f"idea-standalone-{pair[0]}--{pair[1]}")


def make_brief(
    title: str,
    topic: str,
    trick: str | None,
    supporting_papers: list[dict],
    confidence: float,
) -> dict:
    """Create a deliberately provisional, test-oriented brief."""
    technique = trick or "a controlled baseline"
    readable_technique = technique.replace("-", " ")
    readable_topic = topic.replace("-", " ")
    protocol = protocol_for(topic)
    confound = confound_for(trick)
    full_reading_count = sum(
        paper.get("reading_depth") in {"full_text", "verified"}
        for paper in supporting_papers
    )
    routed_count = len(supporting_papers) - full_reading_count
    return {
        "title": title,
        "thesis": (
            f"Test whether {readable_technique} produces a measurable, "
            f"repeatable gain in {readable_topic}."
        ),
        "motivation": (
            f"The linked papers suggest that {readable_technique} may change "
            f"{readable_topic}, but the route is still a hypothesis. The decisive "
            f"comparison is against {protocol['baseline']}."
        ),
        "research_question": (
            f"Under matched compute and data, when does {readable_technique} "
            f"improve {readable_topic}, and when does it fail?"
        ),
        "method": [
            f"Reproduce {protocol['baseline']} and lock the data split, budget, and evaluation harness.",
            f"Add one intervention for {readable_technique}; keep unrelated choices fixed.",
            confound,
            "Choose seed count from a pilot variance estimate, report uncertainty, and preregister the stopping rule.",
            f"Analyze failures by {protocol['failure_slice']}, not only the mean score.",
        ],
        "evaluation": [
            protocol["primary_metric"],
            "Wall-clock time, peak memory, and training or inference compute",
            protocol["heldout"],
            "An ablation that removes the proposed mechanism",
        ],
        "risks": [
            "The connection may be lexical rather than causal; verify the cited methods and limitations.",
            confound,
            "A new experimental scaffold may introduce implementation confounds.",
        ],
        "first_week": [
            "Read the linked papers and record page-level evidence for the claimed mechanism.",
            "Run the unmodified baseline end to end on a reduced dataset.",
            "Write a one-page preregistration with the primary metric and stopping rule.",
        ],
        "paper_ids": [paper["id"] for paper in supporting_papers],
        "repo_ids": [],
        "confidence": confidence,
        "status": "provisional",
        "evidence_note": (
            f"Linked support includes {full_reading_count} page-anchored full "
            f"reading{'s' if full_reading_count != 1 else ''} and {routed_count} "
            "abstract- or metadata-routed record"
            f"{'s' if routed_count != 1 else ''}. Promote only after the claimed "
            "mechanism and competitive landscape are verified."
        ),
    }


def select_supporting_papers(papers: list[dict], limit: int) -> list[dict]:
    """Prefer substantive readings and avoid citing collection duplicates twice."""
    priority = {"verified": 0, "full_text": 1, "abstract": 2, "metadata": 3}
    ordered = sorted(
        papers,
        key=lambda paper: (
            priority.get(paper.get("reading_depth", "metadata"), 4),
            paper.get("stable_id") or paper["id"],
            paper["id"],
        ),
    )
    selected = []
    seen = set()
    for paper in ordered:
        canonical_id = paper.get("stable_id") or paper["id"]
        if canonical_id in seen:
            continue
        selected.append(paper)
        seen.add(canonical_id)
        if len(selected) == limit:
            break
    return selected


def index_paper_support(
    papers: list[dict],
) -> tuple[dict[str, list[dict]], dict[tuple[str, str], list[dict]]]:
    """Index papers by topic and topic-technique pair for deterministic routing."""
    topic_papers: dict[str, list[dict]] = defaultdict(list)
    pair_papers: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for paper in papers:
        topics = {route_id(topic.get("id")) for topic in paper["topics"]}
        tricks = {route_id(trick.get("id")) for trick in paper["tricks"]}
        for topic in sorted(topics):
            topic_papers[topic].append(paper)
            for trick in sorted(tricks):
                pair_papers[(topic, trick)].append(paper)
    return (
        {
            topic: select_supporting_papers(supporting, len(supporting))
            for topic, supporting in topic_papers.items()
        },
        {
            pair: select_supporting_papers(supporting, len(supporting))
            for pair, supporting in pair_papers.items()
        },
    )


def build_cross_ideas(
    pair_papers: dict[tuple[str, str], list[dict]],
) -> list[dict]:
    """Create the highest-support topic-technique screening hypotheses."""
    ideas: list[dict] = []
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for pair, papers in pair_papers.items():
        normalized = (route_id(pair[0]), route_id(pair[1]))
        grouped[normalized].extend(papers)
    unique_pairs = [
        (pair, select_supporting_papers(papers, len(papers)))
        for pair, papers in grouped.items()
    ]
    best_pairs = sorted(
        (item for item in unique_pairs if len(item[1]) >= 2),
        key=lambda item: (-len(item[1]), item[0]),
    )
    retained = [item for item in best_pairs if item[0] in LEGACY_IDS]
    novel = [item for item in best_pairs if item[0] not in LEGACY_IDS]
    best_pairs = [*retained, *novel][:48]
    for (topic, trick), supporting in best_pairs:
        title = f"Stress-test {trick.replace('-', ' ')} for {topic.replace('-', ' ')}"
        selected_support = supporting[:6]
        ideas.append(
            {
                "id": idea_id(topic, trick),
                "kind": "research",
                "origin": "cross-paper",
                "topic_ids": [topic],
                "trick_ids": [trick],
                "repo_ids": [],
                "brief": make_brief(
                    title,
                    topic,
                    trick,
                    selected_support,
                    min(0.82, 0.42 + len(supporting) / 100),
                ),
            }
        )
    return ideas


def build_provisional_ideas(papers: list[dict]) -> list[dict]:
    """Build and score cross-paper candidate ideas from the general corpus."""
    _, pair_papers = index_paper_support(papers)
    ideas = build_cross_ideas(pair_papers)
    for idea in ideas:
        idea["feasibility"] = score_feasibility(idea)
    return ideas


def score_feasibility(idea: dict) -> dict:
    """Score practical testability, not scientific importance."""
    topics = set(idea["topic_ids"])
    is_provisional = idea.get("brief", {}).get("status", "provisional") == "provisional"
    implementation = 1.4
    if topics & {"pre-training", "world-models", "generative-modeling"}:
        compute = 1.0
    elif topics & {"post-training", "agents", "multimodal"}:
        compute = 1.5
    else:
        compute = 2.1
    evaluation = (
        1.9
        if topics
        & {"evaluation", "optimization", "efficiency-systems", "learning-theory"}
        else 1.5
    )
    novelty = 1.0 if idea["origin"] == "cross-paper" else 0.8
    time_to_signal = 1.0
    if topics & {"pre-training", "world-models"}:
        time_to_signal -= 0.4
    if is_provisional:
        # Until full-text and competitive review, metric clarity and novelty are
        # hypotheses rather than established properties of the idea.
        evaluation = min(evaluation, 0.9)
        novelty = min(novelty, 0.3)

    factors = [
        {
            "id": "implementation_leverage",
            "score": implementation,
            "max": FEASIBILITY_FACTOR_MAXIMA["implementation_leverage"],
            "rationale": "Requires a new experimental scaffold from public paper specifications.",
        },
        {
            "id": "compute_and_data",
            "score": compute,
            "max": FEASIBILITY_FACTOR_MAXIMA["compute_and_data"],
            "rationale": (
                "Estimated from the dominant research area; confirm against "
                "the selected baseline."
            ),
        },
        {
            "id": "evaluation_clarity",
            "score": evaluation,
            "max": FEASIBILITY_FACTOR_MAXIMA["evaluation_clarity"],
            "rationale": (
                "Screening estimate pending full-text validation."
                if is_provisional
                else "Standard metrics and controlled comparisons are defined."
            ),
        },
        {
            "id": "novelty_risk",
            "score": novelty,
            "max": FEASIBILITY_FACTOR_MAXIMA["novelty_risk"],
            "rationale": (
                "Capped until the competitive-landscape review is verified."
                if is_provisional
                else "Competitive review leaves a defensible contribution."
            ),
        },
        {
            "id": "time_to_signal",
            "score": time_to_signal,
            "max": FEASIBILITY_FACTOR_MAXIMA["time_to_signal"],
            "rationale": (
                "Estimates whether a reduced experiment can answer the primary "
                "question quickly."
            ),
        },
    ]
    score = round(max(1.0, min(10.0, sum(row["score"] for row in factors))), 1)
    return {
        "score": score,
        "band": "high" if score >= 8 else "medium" if score >= 5.5 else "low",
        "factors": factors,
        "assumptions": [
            "Uses public paper data and evaluation assets.",
            "Measures a reduced baseline before scaling.",
            "Novelty score must be revised after full related-work review.",
        ],
        "screening_estimate": is_provisional,
        "version": "rubric-0.2",
    }
