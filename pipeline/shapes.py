"""Validate common browser-visible idea and research-brief shapes."""

from __future__ import annotations

from math import isfinite

from rules import check, validate_competitor_panel


EXPERIMENT_FIELDS = {
    "primary_hypothesis",
    "secondary_hypothesis",
    "domains",
    "baselines",
    "ablations",
    "primary_outcome",
    "analysis",
    "claim_hierarchy",
    "selection_protocol",
    "resource_scalarization",
    "action_ontology",
    "decision_rule",
}


def is_string_array(value: object) -> bool:
    """Return whether a value is a list containing only strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_experiment_shape(idea_id: str, experiment: object) -> None:
    """Validate the common experiment fields rendered by every brief."""
    check(isinstance(experiment, dict), f"Idea brief has invalid experiment: {idea_id}")
    unknown_fields = set(experiment) - EXPERIMENT_FIELDS
    check(
        not unknown_fields,
        f"Idea brief experiment has unsupported fields {sorted(unknown_fields)}: {idea_id}",
    )
    for field in ("primary_hypothesis", "secondary_hypothesis", "decision_rule"):
        check(
            isinstance(experiment.get(field), str) and experiment[field].strip(),
            f"Idea brief experiment lacks {field}: {idea_id}",
        )
    for field in ("domains", "baselines", "ablations"):
        values = experiment.get(field)
        check(
            isinstance(values, list)
            and bool(values)
            and all(isinstance(value, str) and value.strip() for value in values),
            f"Idea brief experiment lacks {field}: {idea_id}",
        )
    for field in (
        "primary_outcome",
        "analysis",
        "claim_hierarchy",
        "selection_protocol",
        "resource_scalarization",
        "action_ontology",
    ):
        value = experiment.get(field)
        check(
            value is None or (isinstance(value, str) and value.strip()),
            f"Idea brief experiment has invalid {field}: {idea_id}",
        )


def validate_brief_shape(idea_id: str, brief: object) -> None:
    """Validate common browser-visible brief fields before lifecycle checks."""
    check(isinstance(brief, dict), f"Idea brief is not an object: {idea_id}")
    text_fields = (
        "title",
        "thesis",
        "motivation",
        "research_question",
        "evidence_note",
    )
    check(
        all(isinstance(brief.get(field), str) for field in text_fields),
        f"Idea brief has invalid text fields: {idea_id}",
    )
    check(
        isinstance(brief.get("status"), str),
        f"Idea brief status is invalid: {idea_id}",
    )
    list_fields = ("evaluation", "risks", "first_week", "paper_ids", "repo_ids")
    check(
        all(is_string_array(brief.get(field)) for field in list_fields),
        f"Idea brief has invalid list fields: {idea_id}",
    )
    check(
        brief.get("method") is None or is_string_array(brief["method"]),
        f"Idea brief has an invalid method: {idea_id}",
    )
    for field in ("novelty_assessment",):
        check(
            field not in brief
            or (isinstance(brief[field], str) and bool(brief[field].strip())),
            f"Idea brief has invalid {field}: {idea_id}",
        )
    for field in ("non_claims", "subquestions", "falsifiers"):
        check(
            field not in brief or is_string_array(brief[field]),
            f"Idea brief has invalid {field}: {idea_id}",
        )
    confidence = brief.get("confidence")
    check(
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and isfinite(confidence)
        and 0 <= confidence <= 1,
        f"Idea brief confidence is invalid: {idea_id}",
    )
    if brief.get("competitive_landscape") is not None:
        validate_competitor_panel(
            brief["competitive_landscape"],
            minimum=0,
            label=f"Idea brief competitive review for {idea_id}",
            require_provenance=True,
        )
    if brief.get("experiment") is not None:
        validate_experiment_shape(idea_id, brief["experiment"])


def validate_idea_shape(idea: object) -> None:
    """Validate common idea fields shared by every lifecycle state."""
    check(isinstance(idea, dict), "Idea is not an object")
    idea_id = idea.get("id")
    check(
        isinstance(idea_id, str) and bool(idea_id.strip()),
        "Idea has an invalid ID",
    )
    kind = idea.get("kind")
    check(
        isinstance(kind, str) and kind in {"research", "blog"},
        f"Idea kind is invalid: {idea_id}",
    )
    check(isinstance(idea.get("origin"), str), f"Idea origin is invalid: {idea_id}")
    for field in ("topic_ids", "trick_ids", "repo_ids"):
        check(
            is_string_array(idea.get(field)),
            f"Idea has invalid {field}: {idea_id}",
        )
    role = idea.get("portfolio_role")
    parent_id = idea.get("parent_idea_id")
    rank_independently = idea.get("rank_independently")
    check(
        role is None or (isinstance(role, str) and role in {"program", "work-package"}),
        f"Idea portfolio role is invalid: {idea_id}",
    )
    check(
        parent_id is None or (isinstance(parent_id, str) and bool(parent_id.strip())),
        f"Idea parent ID is invalid: {idea_id}",
    )
    check(
        rank_independently is None or isinstance(rank_independently, bool),
        f"Idea ranking flag is invalid: {idea_id}",
    )
    check(
        isinstance(idea.get("feasibility"), dict),
        f"Idea feasibility is invalid: {idea_id}",
    )
    validate_brief_shape(idea_id, idea.get("brief"))
