"""Validate research-brief structure, scores, and portfolio relationships."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from jsonschema import Draft202012Validator

from ideas import (
    BRIEF_STATUSES,
    FEASIBILITY_FACTOR_MAXIMA,
    IDEA_ORIGINS,
    PROVISIONAL_FACTOR_CAPS,
)
from ontology import TOPICS, TRICKS
from privacy import LOCAL_PATH, PERSONAL_SOCIAL, text_values
from rules import check, validate_competitor_panel, validate_schema
from shapes import validate_experiment_shape, validate_idea_shape


ROOT = Path(__file__).resolve().parents[1]
FEASIBILITY_SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/feasibility.schema.json").read_text(encoding="utf-8"))
)
IDEA_FIELDS = {
    "id",
    "kind",
    "origin",
    "topic_ids",
    "trick_ids",
    "repo_ids",
    "brief",
    "feasibility",
    "portfolio_role",
    "parent_idea_id",
    "rank_independently",
}
BRIEF_FIELDS = {
    "title",
    "thesis",
    "motivation",
    "research_question",
    "method",
    "evaluation",
    "risks",
    "first_week",
    "paper_ids",
    "repo_ids",
    "confidence",
    "status",
    "evidence_note",
    "non_claims",
    "subquestions",
    "generation_routes",
    "core_design",
    "what_counts_as_learning_signal",
    "validation_funnel",
    "human_in_the_loop",
    "scaling_claim_protocol",
    "experiment",
    "reading_roles",
    "route_dictionary_protocol",
    "milestones",
    "falsifiers",
    "competitive_landscape",
    "novelty_assessment",
}
EMAIL = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![a-z0-9.-])"
)
SOCIAL_HANDLE = re.compile(r"(?i)(?<![a-z0-9_])@[a-z0-9_]{2,32}(?![a-z0-9_])")
SOCIAL_URL = re.compile(
    r"(?i)https?://(?:www\.)?(?:bsky\.app|facebook\.com|instagram\.com|"
    r"linkedin\.com|mastodon\.social|threads\.net|tiktok\.com)/"
)
FILE_URI = re.compile(r"(?i)(?:^|[^a-z0-9])file://")
UNSAFE_CATEGORIES = {"Cc", "Cf", "Cs"}


def unsafe_text(text: str) -> bool:
    """Detect identity-bearing or display-manipulating candidate text."""
    return (
        LOCAL_PATH.search(text) is not None
        or FILE_URI.search(text) is not None
        or EMAIL.search(text) is not None
        or PERSONAL_SOCIAL.search(text) is not None
        or SOCIAL_URL.search(text) is not None
        or SOCIAL_HANDLE.search(text) is not None
        or any(
            unicodedata.category(character) in UNSAFE_CATEGORIES for character in text
        )
    )


def validate_idea_boundary(idea: object) -> None:
    """Close idea fields and screen unreviewed synthesis without echoing content."""
    check(isinstance(idea, dict), "Idea boundary requires an object")
    origin = idea.get("origin")
    brief = idea.get("brief")
    feasibility = idea.get("feasibility")
    status = brief.get("status") if isinstance(brief, dict) else None
    if origin == "cross-paper":
        check(
            all(not unsafe_text(text) for _, text in text_values(idea)),
            "Automatically generated idea contains unsafe text",
        )
        check(
            status == "provisional"
            and isinstance(feasibility, dict)
            and feasibility.get("screening_estimate") is True,
            "Automatically generated idea must remain provisional screening material",
        )
        check(
            isinstance(brief, dict)
            and "novelty_assessment" not in brief
            and "competitive_landscape" not in brief,
            "Automatically generated idea cannot claim reviewed evidence",
        )
    if status == "researched-draft":
        check(
            origin in {"cross-paper-reviewed", "user-specified"},
            "Researched idea requires an authorized reviewed origin",
        )
    check(
        set(idea) <= IDEA_FIELDS,
        "Idea contains unsupported top-level fields",
    )


def validate_feasibility(idea: dict) -> None:
    """Validate one auditable one-decimal feasibility score."""
    check(
        idea.get("origin") in IDEA_ORIGINS,
        f"Unknown idea origin: {idea.get('id', 'unknown')}",
    )
    check(
        idea.get("brief", {}).get("status") in BRIEF_STATUSES,
        f"Unknown brief status: {idea.get('id', 'unknown')}",
    )
    feasibility = idea.get("feasibility", {})
    validate_schema(FEASIBILITY_SCHEMA, feasibility, f"Feasibility {idea['id']}")
    score = feasibility.get("score")
    check(
        isinstance(score, (int, float))
        and 1 <= score <= 10
        and round(score, 1) == score,
        f"Invalid feasibility score: {idea['id']}",
    )
    check(
        len(feasibility.get("factors", [])) == 5,
        f"Feasibility rationale incomplete: {idea['id']}",
    )
    check(
        all(
            round(factor["score"], 1) == factor["score"]
            and factor["score"] <= factor["max"]
            for factor in feasibility["factors"]
        ),
        f"Feasibility factor exceeds its maximum: {idea['id']}",
    )
    factors_by_id = {factor["id"]: factor for factor in feasibility["factors"]}
    check(
        set(factors_by_id) == set(FEASIBILITY_FACTOR_MAXIMA)
        and all(
            factors_by_id[factor_id]["max"] == maximum
            for factor_id, maximum in FEASIBILITY_FACTOR_MAXIMA.items()
        ),
        f"Feasibility rubric factors drifted: {idea['id']}",
    )
    if idea.get("brief", {}).get("status") == "provisional":
        check(
            feasibility.get("screening_estimate") is True
            and all(
                factors_by_id[factor_id]["score"] <= cap
                for factor_id, cap in PROVISIONAL_FACTOR_CAPS.items()
            ),
            f"Provisional feasibility exceeds its evidence caps: {idea['id']}",
        )
    factor_total = round(
        sum(factor.get("score", 0) for factor in feasibility["factors"]), 1
    )
    check(factor_total == score, f"Feasibility factors do not sum for {idea['id']}")
    expected_band = "high" if score >= 8 else "medium" if score >= 5.5 else "low"
    check(
        feasibility.get("band") == expected_band,
        f"Feasibility band is stale for {idea['id']}",
    )


def is_string_list(value: object) -> bool:
    """Return whether a protocol list carries at least one readable statement."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def validate_env_protocols(idea_id: str, brief: dict) -> None:
    """Validate the structured environment-generation and signal definitions."""
    generation_routes = brief.get("generation_routes")
    if generation_routes is not None:
        required = {"route", "mechanism", "examples", "best_when"}
        check(
            isinstance(generation_routes, list)
            and bool(generation_routes)
            and all(
                isinstance(route, dict)
                and set(route) == required
                and all(
                    isinstance(route[field], str) and route[field].strip()
                    for field in required
                )
                for route in generation_routes
            ),
            f"Idea generation routes are invalid: {idea_id}",
        )

    core_design = brief.get("core_design")
    if core_design is not None:
        required = {
            "unit_of_search",
            "generator",
            "fitness",
            "selection",
            "critical_control",
        }
        check(
            isinstance(core_design, dict)
            and set(core_design) == required
            and all(
                isinstance(core_design[field], str) and core_design[field].strip()
                for field in required - {"fitness"}
            )
            and is_string_list(core_design.get("fitness")),
            f"Idea core design is invalid: {idea_id}",
        )

    learning_signal = brief.get("what_counts_as_learning_signal")
    if learning_signal is None:
        return
    required = {"answer", "evidence_hierarchy", "recommended_statistics"}
    hierarchy = (
        learning_signal.get("evidence_hierarchy")
        if isinstance(learning_signal, dict)
        else None
    )
    hierarchy_fields = {"level", "name", "evidence", "does_not_show"}
    check(
        isinstance(learning_signal, dict)
        and set(learning_signal) == required
        and isinstance(learning_signal.get("answer"), str)
        and learning_signal["answer"].strip()
        and is_string_list(learning_signal.get("recommended_statistics"))
        and isinstance(hierarchy, list)
        and bool(hierarchy)
        and all(
            isinstance(level, dict)
            and set(level) == hierarchy_fields
            and isinstance(level.get("level"), int)
            and not isinstance(level["level"], bool)
            and level["level"] > 0
            and all(
                isinstance(level[field], str) and level[field].strip()
                for field in hierarchy_fields - {"level"}
            )
            for level in hierarchy
        )
        and len({level["level"] for level in hierarchy}) == len(hierarchy),
        f"Idea learning signal definition is invalid: {idea_id}",
    )


def validate_human_scale(idea_id: str, brief: dict) -> None:
    """Require decision-bearing HITL and scaling claims rather than empty shells."""
    human = brief.get("human_in_the_loop")
    if human is not None:
        allowed = {
            "answer",
            "short_answer",
            "policy",
            "routing_policy",
            "measurement",
            "humans_not_needed_for",
            "humans_needed_for",
        }
        decisions = (
            human.get("answer") if isinstance(human, dict) else None,
            human.get("short_answer") if isinstance(human, dict) else None,
        )
        check(
            isinstance(human, dict)
            and set(human) <= allowed
            and any(isinstance(value, str) and value.strip() for value in decisions)
            and isinstance(human.get("measurement"), str)
            and human["measurement"].strip()
            and is_string_list(human.get("humans_not_needed_for"))
            and is_string_list(human.get("humans_needed_for"))
            and all(
                field not in human
                or (isinstance(human[field], str) and human[field].strip())
                for field in ("answer", "short_answer", "policy", "routing_policy")
            ),
            f"Idea human-in-the-loop protocol is invalid: {idea_id}",
        )

    scaling = brief.get("scaling_claim_protocol")
    if scaling is None:
        return
    allowed = {
        "answer",
        "short_answer",
        "minimum_design",
        "prospective_design",
        "supporting_evidence",
        "claim_blockers",
        "why_small_models_fail",
        "claim_language",
    }
    decisions = (
        scaling.get("answer") if isinstance(scaling, dict) else None,
        scaling.get("short_answer") if isinstance(scaling, dict) else None,
    )
    check(
        isinstance(scaling, dict)
        and set(scaling) <= allowed
        and any(isinstance(value, str) and value.strip() for value in decisions)
        and is_string_list(scaling.get("supporting_evidence"))
        and is_string_list(scaling.get("claim_blockers"))
        and all(
            field not in scaling
            or (isinstance(scaling[field], str) and scaling[field].strip())
            for field in ("answer", "short_answer", "minimum_design", "claim_language")
        )
        and all(
            field not in scaling or is_string_list(scaling[field])
            for field in ("prospective_design", "why_small_models_fail")
        ),
        f"Idea scaling claim protocol is invalid: {idea_id}",
    )


def validate_brief_protocols(idea_id: str, brief: dict) -> None:
    """Validate specialized brief structures so browser-visible detail is not lost."""
    unknown_fields = set(brief) - BRIEF_FIELDS
    check(
        not unknown_fields,
        f"Idea brief has unsupported fields {sorted(unknown_fields)}: {idea_id}",
    )
    validate_env_protocols(idea_id, brief)
    validate_human_scale(idea_id, brief)

    validation_funnel = brief.get("validation_funnel")
    if validation_funnel is not None:
        check(
            isinstance(validation_funnel, list)
            and bool(validation_funnel)
            and all(
                isinstance(stage, dict)
                and set(stage) == {"stage", "cost", "gate"}
                and all(
                    isinstance(stage[field], str) and stage[field].strip()
                    for field in ("stage", "cost", "gate")
                )
                for stage in validation_funnel
            ),
            f"Idea validation funnel is invalid: {idea_id}",
        )

    reading_roles = brief.get("reading_roles")
    if reading_roles is not None:
        check(
            isinstance(reading_roles, list)
            and all(
                isinstance(role, dict)
                and set(role) == {"paper_id", "role", "use"}
                and all(
                    isinstance(role[field], str) and role[field].strip()
                    for field in ("paper_id", "role", "use")
                )
                for role in reading_roles
            ),
            f"Idea reading roles are invalid: {idea_id}",
        )
        role_ids = [role["paper_id"] for role in reading_roles]
        paper_ids = brief.get("paper_ids", [])
        check(
            len(role_ids) == len(set(role_ids))
            and set(role_ids) == set(paper_ids)
            and len(role_ids) == len(paper_ids),
            f"Idea reading roles do not exactly cover evidence papers: {idea_id}",
        )

    route_dictionary = brief.get("route_dictionary_protocol")
    if route_dictionary is not None:
        list_fields = {
            "shared_axes",
            "markov_family",
            "regression_family",
            "invalidation_rules",
        }
        check(
            isinstance(route_dictionary, dict)
            and set(route_dictionary) == list_fields | {"freeze_boundary"}
            and isinstance(route_dictionary.get("freeze_boundary"), str)
            and route_dictionary["freeze_boundary"].strip()
            and all(
                isinstance(route_dictionary.get(field), list)
                and bool(route_dictionary[field])
                and all(
                    isinstance(value, str) and value.strip()
                    for value in route_dictionary[field]
                )
                for field in list_fields
            ),
            f"Idea route dictionary protocol is invalid: {idea_id}",
        )

    milestones = brief.get("milestones")
    if milestones is not None:
        check(
            isinstance(milestones, list)
            and bool(milestones)
            and all(
                isinstance(milestone, dict)
                and set(milestone) == {"name", "deliverable", "pass_condition"}
                and all(
                    isinstance(milestone[field], str) and milestone[field].strip()
                    for field in ("name", "deliverable", "pass_condition")
                )
                for milestone in milestones
            ),
            f"Idea milestones are invalid: {idea_id}",
        )


def validate_experiment_plan(idea_id: str, experiment: object) -> None:
    """Require a decisive, inspectable experiment for a promoted brief."""
    validate_experiment_shape(idea_id, experiment)
    check(
        isinstance(experiment.get("primary_outcome"), str)
        and bool(experiment["primary_outcome"].strip()),
        f"Researched brief experiment lacks primary_outcome: {idea_id}",
    )


def validate_researched_brief(idea: dict, full_reading_ids: set[str]) -> None:
    """Keep promoted briefs meaningfully above the provisional screening tier."""
    brief = idea.get("brief", {})
    check(isinstance(brief, dict), f"Idea brief is not an object: {idea['id']}")
    validate_brief_protocols(idea["id"], brief)
    if brief.get("status") != "researched-draft":
        return
    method_is_present = is_string_list(brief.get("method")) or isinstance(
        brief.get("core_design"), dict
    )
    check(method_is_present, f"Researched brief lacks method: {idea['id']}")
    for field in ("evaluation", "risks", "first_week"):
        check(
            is_string_list(brief.get(field)),
            f"Researched brief lacks {field}: {idea['id']}",
        )
    validate_experiment_plan(idea["id"], brief.get("experiment"))
    competitors = brief.get("competitive_landscape", [])
    validate_competitor_panel(
        competitors,
        minimum=5,
        label=f"Researched brief competitive review for {idea['id']}",
        require_provenance=True,
    )
    check(
        bool(brief.get("novelty_assessment")),
        f"Researched brief lacks a novelty assessment: {idea['id']}",
    )
    check(
        isinstance(brief.get("confidence"), (int, float))
        and 0 <= brief["confidence"] <= 1,
        f"Researched brief confidence is invalid: {idea['id']}",
    )
    check(
        idea.get("feasibility", {}).get("screening_estimate") is not True,
        f"Researched brief is still marked as a screening estimate: {idea['id']}",
    )
    read_support = set(brief.get("paper_ids", [])) & full_reading_ids
    user_exception = idea.get("origin") == "user-specified" and len(competitors) >= 10
    check(
        len(read_support) >= 2 or user_exception,
        f"Researched brief lacks multiple full-reading supports: {idea['id']}",
    )


def validate_portfolio_hierarchy(ideas: list[dict]) -> None:
    """Keep programs and subordinate work packages explicit and non-ambiguous."""
    ideas_by_id = {idea.get("id"): idea for idea in ideas}
    for idea in ideas:
        idea_id = idea.get("id", "<missing>")
        role = idea.get("portfolio_role")
        parent_id = idea.get("parent_idea_id")
        rank_independently = idea.get("rank_independently")
        if role is None:
            check(
                parent_id is None and rank_independently is None,
                f"Portfolio metadata lacks a role: {idea_id}",
            )
            continue
        check(
            role in {"program", "work-package"}, f"Unknown portfolio role on {idea_id}"
        )
        if role == "program":
            check(
                parent_id is None and rank_independently is True,
                f"Program hierarchy metadata is inconsistent: {idea_id}",
            )
            continue
        check(
            isinstance(parent_id, str) and rank_independently is False,
            f"Work-package hierarchy metadata is inconsistent: {idea_id}",
        )
        parent = ideas_by_id.get(parent_id)
        check(
            parent is not None and parent.get("portfolio_role") == "program",
            f"Work-package parent is unresolved or not a program: {idea_id}",
        )


def validate_idea_references(
    atlas: dict,
    repo_ids: set[str],
    full_reading_ids: set[str],
) -> None:
    """Validate idea foreign keys, brief contracts, and auditable scores."""
    check(
        any(item["id"] == "flagship-evo-rl-environments" for item in atlas["ideas"]),
        "Flagship RL environment idea is missing",
    )
    paper_reference_ids = {
        identifier
        for paper in atlas["papers"]
        for identifier in (paper["id"], paper.get("stable_id"))
        if identifier
    }
    for idea in atlas["ideas"]:
        validate_idea_boundary(idea)
        validate_idea_shape(idea)
    validate_portfolio_hierarchy(atlas["ideas"])
    for idea in atlas["ideas"]:
        check(
            set(idea.get("topic_ids", [])) <= set(TOPICS),
            f"Unknown idea topic: {idea['id']}",
        )
        check(
            set(idea.get("trick_ids", [])) <= set(TRICKS),
            f"Unknown idea technique: {idea['id']}",
        )
        check(
            set(idea.get("repo_ids", [])) <= repo_ids,
            f"Unknown idea repository: {idea['id']}",
        )
        brief = idea.get("brief", {})
        check(
            set(brief.get("paper_ids", [])) <= paper_reference_ids,
            f"Idea contains unresolved collection paper IDs: {idea['id']}",
        )
        check(
            all(
                brief.get(field)
                for field in ("title", "thesis", "research_question", "status")
            ),
            f"Idea brief contract incomplete: {idea['id']}",
        )
        validate_feasibility(idea)
        validate_researched_brief(idea, full_reading_ids)
