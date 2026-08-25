"""Pure helpers for creating provisional ideas and feasibility scores."""

from __future__ import annotations

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
        for topic in paper["topics"]:
            topic_papers[topic["id"]].append(paper)
            for trick in paper["tricks"]:
                pair_papers[(topic["id"], trick["id"])].append(paper)
    return topic_papers, pair_papers


def build_cross_ideas(
    pair_papers: dict[tuple[str, str], list[dict]],
) -> list[dict]:
    """Create the highest-support topic-technique screening hypotheses."""
    ideas: list[dict] = []
    best_pairs = sorted(pair_papers.items(), key=lambda item: (-len(item[1]), item[0]))[
        :48
    ]
    for index, ((topic, trick), supporting) in enumerate(best_pairs, start=1):
        title = f"Stress-test {trick.replace('-', ' ')} for {topic.replace('-', ' ')}"
        selected_support = select_supporting_papers(supporting, 6)
        ideas.append(
            {
                "id": f"idea-standalone-{index}",
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
