from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from ideas import score_feasibility  # noqa: E402
from ontology import TOPICS, TRICKS  # noqa: E402
from assign import build_reading_queue  # noqa: E402
from verify import build_verification_queue  # noqa: E402
from assets import reading_public_path  # noqa: E402
from scholar import cache_text  # noqa: E402
from privacy import public_reviewer_id, unsafe_public, validate_public  # noqa: E402
from validate import (  # noqa: E402
    is_primary_url,
    validate_anchor_routes,
    validate_competitor_panel,
    validate_experiment_plan,
    validate_feasibility,
    validate_fulltext_integrity,
    validate_idea_shape,
    validate_progress,
    validate_paper_routes,
    validate_taxonomy_counts,
    validate_brief_protocols,
    validate_portfolio_hierarchy,
    validate_reading,
    validate_review_queues,
    validate_researched_brief,
    validate_source_routes,
)


def valid_reading() -> dict:
    return {
        "stable_id": "arxiv:1",
        "reading_depth": "full_text",
        "source_provenance": {
            "source_locator": "https://arxiv.org/pdf/1",
            "pdf_sha256": "a" * 64,
            "text_sha256": "b" * 64,
            "page_count": 8,
            "extracted_at": "2026-08-23T00:00:00+00:00",
            "review_pass": "primary-full-text-v1",
        },
        "question": "Question",
        "key_findings": [
            {
                "claim": "Claim",
                "evidence": "Evidence",
                "anchors": [{"page": 1, "section": "1"}],
            }
        ],
        "method": {"core_idea": "x", "mechanism": "y", "assumptions": []},
        "techniques": [],
        "evaluations": [],
        "limitations": [],
        "failure_modes": [],
        "reusable_insights": [],
        "open_questions": [],
        "competitive_landscape": [
            {
                "canonical_id": f"arxiv:prior-{index}",
                "title": "Prior",
                "url": f"https://arxiv.org/abs/prior-{index}",
                "relationship": "prior",
                "difference": "Direct difference",
            }
            for index in range(3)
        ],
        "novelty_assessment": "Narrow novelty",
        "confidence": 0.8,
        "reviewer_notes": "Notes",
    }


def valid_fulltext_entry(stable_id: str = "arxiv:1") -> dict:
    return {
        "stable_id": stable_id,
        "source_route": "arxiv",
        "pdf_url": "https://arxiv.org/pdf/1",
        "pdf_sha256": "a" * 64,
        "page_count": 10,
        "text_path": "data/cache/text/nonexistent-test-fixture.txt",
        "processed_at": "2026-08-23T00:00:00+00:00",
        "status": "full_text_ok",
        "text_sha256": "b" * 64,
        "character_count": 20_000,
        "useful_character_count": 10_000,
        "pages_with_text": 9,
        "missing_text_pages": [10],
        "text_coverage_ratio": 0.9,
        "useful_character_ratio": 0.9,
    }


def valid_idea() -> dict:
    return {
        "id": "idea-1",
        "kind": "research",
        "origin": "cross-paper",
        "topic_ids": ["agents"],
        "trick_ids": [],
        "repo_ids": [],
        "feasibility": {},
        "brief": {
            "title": "Test an intervention",
            "thesis": "The intervention has a measurable effect.",
            "motivation": "The current evidence is incomplete.",
            "research_question": "Does the intervention work?",
            "method": ["Run a matched comparison."],
            "evaluation": ["Measure the registered outcome."],
            "risks": ["The effect may not transfer."],
            "first_week": ["Build the fixture."],
            "paper_ids": ["arxiv:1"],
            "repo_ids": [],
            "confidence": 0.6,
            "status": "provisional",
            "evidence_note": "This is a screening proposal.",
        },
    }


class PrimarySourceUrlTests(unittest.TestCase):
    def test_primary_hosts(self) -> None:
        for url in (
            "https://arxiv.org/abs/2401.00001",
            "https://proceedings.mlr.press/v235/example.html",
            "https://dl.acm.org/doi/10.1145/example",
            "https://journals.aps.org/pre/abstract/10.1103/PhysRevE.104.034304",
            "https://www.ijcai.org/proceedings/2023/406",
            "https://proceedings.nips.cc/paper_files/paper/2025/hash/example.html",
            "https://ojs.aaai.org/index.php/AAAI/article/view/34008",
            "https://elifesciences.org/articles/68344",
            "https://www.sciencedirect.com/science/article/pii/S0045782598000933",
        ):
            with self.subTest(url=url):
                self.assertTrue(is_primary_url(url))

    def test_rejected_hosts(self) -> None:
        self.assertFalse(is_primary_url("http://arxiv.org/abs/2401.00001"))
        self.assertFalse(is_primary_url("https://example.com/paper"))


class PrivacyTests(unittest.TestCase):
    def test_reviewer_identity(self) -> None:
        first = public_reviewer_id("arxiv:1", "2026-08-23")
        second = public_reviewer_id("arxiv:1", "2026-08-23")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^reviewer-[0-9a-f]{12}$")
        validate_public({"verification": {"reviewer_id": first}}, "fixture")

    def test_private_metadata(self) -> None:
        home_path = "/" + "Users/account/research.pdf"
        social_url = "https://" + "x.com/account/status/1"
        cases = (
            ({"notes": home_path}, "local device path"),
            ({"notes": "／Users／account／research.pdf"}, "local device path"),
            ({"source": social_url}, "personal social URL"),
            (
                {"source": "https：／／x.com／account／status／1"},
                "personal social URL",
            ),
            ({"comment": "Contact author@example.edu"}, "email address"),
            ({"comment": "Contact author@example. edu"}, "email address"),
            ({"comment": "Contact author@example. EDU"}, "email address"),
            ({"comment": "Contact author＠example.edu"}, "email address"),
            ({"authors": ["owner@localhost"]}, "email address"),
            ({"authors": ["owner@example. COM"]}, "email address"),
            (
                {"verification": {"reviewer_id": "not-opaque"}},
                "reviewer ID",
            ),
        )
        for value, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    validate_public(value, "fixture")

    def test_metric_prose(self) -> None:
        for text in (
            "Recall@10. On held-out data",
            "NDCG@20. These results",
            "Recall@K. On held-out data",
            "Precision@k. The score",
            "Hits@N. We report",
            "Pass@K. This improves robustness",
            "Recall@k. Results follow",
            "Recall@K. Net performance improves",
            "Pass@N. Org results follow",
            "Metric@scale. Com performance",
            "Score@model. Edu results",
        ):
            with self.subTest(text=text):
                self.assertFalse(unsafe_public(text))

    def test_email_period(self) -> None:
        self.assertTrue(unsafe_public("Mail ada@example.edu."))
        self.assertTrue(unsafe_public("Mail owner@localhost."))
        self.assertFalse(unsafe_public("Metric ada@example.edu.123 remains"))
        self.assertTrue(unsafe_public("Contact ada@example. EDU"))

    def test_taxonomy_text(self) -> None:
        for kind in ("topics", "tricks"):
            with self.subTest(kind=kind):
                atlas = {
                    "topics": [
                        {"id": key, "label": key, "paper_count": 0} for key in TOPICS
                    ],
                    "tricks": [
                        {"id": key, "label": key, "paper_count": 0} for key in TRICKS
                    ],
                }
                atlas[kind][0]["label"] = "Contact author@example.org"

                with self.assertRaisesRegex(RuntimeError, f"Public {kind}.*unsafe"):
                    validate_taxonomy_counts(atlas, [])


class ValidationTests(unittest.TestCase):
    def test_committed_anchor_routes_match_published_atlas(self) -> None:
        root = Path(__file__).resolve().parents[1]
        validate_anchor_routes(
            root / "data/source/anchors.npz",
            root / "web/public/data/atlas.json",
        )

    def test_idea_shape(self) -> None:
        validate_idea_shape(valid_idea())
        cases = (
            (("kind",), {"unsafe": True}),
            (("topic_ids",), [1]),
            (("brief", "confidence"), "high"),
            (("brief", "evaluation"), [1]),
            (("brief", "method"), [False]),
            (("brief", "non_claims"), [1]),
        )
        for path, invalid in cases:
            idea = valid_idea()
            target = idea
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = invalid
            with self.subTest(path=path):
                with self.assertRaises(RuntimeError):
                    validate_idea_shape(idea)

        for field in ("motivation", "evidence_note"):
            idea = valid_idea()
            del idea["brief"][field]
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeError, "text fields"):
                    validate_idea_shape(idea)

    def test_portfolio_hierarchy(self) -> None:
        ideas = [
            {
                "id": "program",
                "portfolio_role": "program",
                "rank_independently": True,
            },
            {
                "id": "validator",
                "portfolio_role": "work-package",
                "parent_idea_id": "program",
                "rank_independently": False,
            },
            {"id": "standalone"},
        ]
        validate_portfolio_hierarchy(ideas)

        ideas[1]["rank_independently"] = True
        with self.assertRaisesRegex(RuntimeError, "hierarchy metadata"):
            validate_portfolio_hierarchy(ideas)
        ideas[1]["rank_independently"] = False

        ideas[1]["parent_idea_id"] = "standalone"
        with self.assertRaisesRegex(RuntimeError, "not a program"):
            validate_portfolio_hierarchy(ideas)

    def test_brief_protocols(self) -> None:
        brief = {
            "paper_ids": ["arxiv:1"],
            "reading_roles": [
                {"paper_id": "arxiv:1", "role": "support", "use": "Boundary"}
            ],
            "validation_funnel": [
                {"stage": "Basis", "cost": "low", "gate": "Recover routes"}
            ],
            "route_dictionary_protocol": {
                "shared_axes": ["lookup versus inference"],
                "markov_family": ["unigram"],
                "regression_family": ["ridge"],
                "freeze_boundary": "Hash before confirmation.",
                "invalidation_rules": ["Abstain when collinear."],
            },
            "milestones": [
                {
                    "name": "Basis audit",
                    "deliverable": "Pinned routes",
                    "pass_condition": "All controls pass",
                }
            ],
        }
        validate_brief_protocols("idea", brief)

        duplicate_role = {**brief, "reading_roles": brief["reading_roles"] * 2}
        with self.assertRaisesRegex(RuntimeError, "exactly cover"):
            validate_brief_protocols("idea", duplicate_role)

        unsupported = {**brief, "invisible_protocol": "must fail"}
        with self.assertRaisesRegex(RuntimeError, "unsupported fields"):
            validate_brief_protocols("idea", unsupported)

        malformed_funnel = {**brief, "validation_funnel": ["untyped gate"]}
        with self.assertRaisesRegex(RuntimeError, "funnel is invalid"):
            validate_brief_protocols("idea", malformed_funnel)
        empty_funnel = {**brief, "validation_funnel": []}
        with self.assertRaisesRegex(RuntimeError, "funnel is invalid"):
            validate_brief_protocols("idea", empty_funnel)

        malformed_dictionary = {
            **brief,
            "route_dictionary_protocol": {
                **brief["route_dictionary_protocol"],
                "shared_axes": [],
            },
        }
        with self.assertRaisesRegex(RuntimeError, "dictionary protocol"):
            validate_brief_protocols("idea", malformed_dictionary)

        malformed_milestone = {
            **brief,
            "milestones": [{"name": "Missing fields"}],
        }
        with self.assertRaisesRegex(RuntimeError, "milestones are invalid"):
            validate_brief_protocols("idea", malformed_milestone)

    def test_env_protocols(self) -> None:
        brief = {
            "generation_routes": [
                {
                    "route": "mutation",
                    "mechanism": "Mutate a typed environment genome.",
                    "examples": "Grid layouts",
                    "best_when": "A simulator is cheap.",
                }
            ],
            "core_design": {
                "unit_of_search": "Immutable environment",
                "generator": "Typed mutation operators",
                "fitness": ["Sealed transfer uplift"],
                "selection": "Successive halving",
                "critical_control": "Equal-compute replacement",
            },
            "what_counts_as_learning_signal": {
                "answer": "A causal training effect on a sealed outcome.",
                "evidence_hierarchy": [
                    {
                        "level": 1,
                        "name": "Operational",
                        "evidence": "Property tests pass.",
                        "does_not_show": "That training learns.",
                    }
                ],
                "recommended_statistics": ["Marginal transfer uplift"],
            },
            "human_in_the_loop": {
                "answer": "Humans adjudicate only ambiguous safety cases.",
                "humans_not_needed_for": ["Deterministic property tests"],
                "humans_needed_for": ["Ambiguous semantic validity"],
                "measurement": "Reviewer agreement and escalation rate",
            },
            "scaling_claim_protocol": {
                "answer": "A small run is a proxy, not a scaling claim.",
                "prospective_design": ["Freeze a predictor before the target tier."],
                "supporting_evidence": ["Target-tier calibration"],
                "claim_blockers": ["Rank reversal"],
                "claim_language": "Evidence within the tested range only.",
            },
        }
        validate_brief_protocols("idea", brief)

        invalid_cases = (
            ({**brief, "generation_routes": []}, "generation routes"),
            (
                {**brief, "core_design": {**brief["core_design"], "fitness": []}},
                "core design",
            ),
            (
                {
                    **brief,
                    "what_counts_as_learning_signal": {
                        **brief["what_counts_as_learning_signal"],
                        "evidence_hierarchy": [],
                    },
                },
                "learning signal",
            ),
            (
                {
                    **brief,
                    "human_in_the_loop": {
                        **brief["human_in_the_loop"],
                        "humans_needed_for": [],
                    },
                },
                "human-in-the-loop",
            ),
            (
                {
                    **brief,
                    "scaling_claim_protocol": {
                        **brief["scaling_claim_protocol"],
                        "claim_blockers": [""],
                    },
                },
                "scaling claim",
            ),
        )
        for invalid, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    validate_brief_protocols("idea", invalid)

    def test_experiment_contract(self) -> None:
        experiment = {
            "primary_hypothesis": "The intervention works.",
            "secondary_hypothesis": "The effect transfers.",
            "domains": ["Held-out tasks"],
            "baselines": ["Matched control"],
            "ablations": ["Remove route"],
            "primary_outcome": "Sealed route forecast score",
            "decision_rule": "Reject when the registered gate fails.",
        }
        validate_experiment_plan("idea", experiment)

        missing_outcome = {**experiment}
        del missing_outcome["primary_outcome"]
        with self.assertRaisesRegex(RuntimeError, "lacks primary_outcome"):
            validate_experiment_plan("idea", missing_outcome)

        hidden_field = {**experiment, "unrendered_result": "must fail"}
        with self.assertRaisesRegex(RuntimeError, "unsupported fields"):
            validate_experiment_plan("idea", hidden_field)

    def test_competitors(self) -> None:
        competitor = {
            "canonical_id": "arxiv:1",
            "title": "Primary paper",
            "url": "https://arxiv.org/abs/1",
            "relationship": "closest prior",
            "difference": "The proposal adds a sealed test.",
            "source_version": "arXiv:1v2",
            "source_date": "2026-08-01",
            "checked_at": "2026-08-23",
        }
        validate_competitor_panel([competitor], minimum=1, label="Panel")

        with self.assertRaisesRegex(RuntimeError, "source provenance"):
            validate_competitor_panel(
                [{**competitor, "source_date": 20260801}],
                minimum=1,
                label="Panel",
            )

        with self.assertRaisesRegex(RuntimeError, "unsupported fields"):
            validate_competitor_panel(
                [{**competitor, "hidden_claim": "must not bypass the contract"}],
                minimum=1,
                label="Panel",
            )

        with self.assertRaisesRegex(RuntimeError, "canonical ID and URL mismatch"):
            validate_competitor_panel(
                [{**competitor, "url": "https://arxiv.org/abs/2"}],
                minimum=1,
                label="Panel",
            )

        mismatched_archives = (
            {
                **competitor,
                "canonical_id": "openreview:correct",
                "url": "https://openreview.net/forum?id=wrong",
                "source_kind": "openreview",
            },
            {
                **competitor,
                "canonical_id": "pmlr:v1-correct",
                "url": "https://proceedings.mlr.press/v1/wrong.html",
                "source_kind": "official-proceedings",
            },
        )
        for mismatch in mismatched_archives:
            with self.subTest(canonical_id=mismatch["canonical_id"]):
                with self.assertRaisesRegex(
                    RuntimeError, "canonical ID and URL mismatch"
                ):
                    validate_competitor_panel([mismatch], minimum=1, label="Panel")

        with self.assertRaisesRegex(RuntimeError, "source kind and URL mismatch"):
            validate_competitor_panel(
                [{**competitor, "source_kind": "openreview"}],
                minimum=1,
                label="Panel",
            )

        with self.assertRaisesRegex(RuntimeError, "invalid source dates"):
            validate_competitor_panel(
                [{**competitor, "checked_at": "yesterday"}],
                minimum=1,
                label="Panel",
            )

        validate_competitor_panel(
            [
                {
                    **competitor,
                    "url": "https://proceedings.mlr.press/v1/final.html",
                    "source_kind": "official-proceedings",
                }
            ],
            minimum=1,
            label="Panel",
        )

        validate_competitor_panel(
            [
                {
                    **competitor,
                    "canonical_id": "pmlr:v1-final",
                    "url": "https://proceedings.mlr.press/v1/final.html",
                    "source_kind": "official-proceedings",
                }
            ],
            minimum=1,
            label="Panel",
        )

    def test_provenance_states(self) -> None:
        competitor = {
            "canonical_id": "arxiv:1",
            "title": "Primary paper",
            "url": "https://arxiv.org/abs/1v2",
            "relationship": "closest prior",
            "difference": "The proposal adds a sealed test.",
            "provenance_status": "version-verified",
            "source_kind": "arxiv",
            "source_version": "arXiv:1v2",
            "source_date": "2026-08-01",
            "checked_at": "2026-08-23",
        }
        validate_competitor_panel(
            [competitor], minimum=1, label="Panel", require_provenance=True
        )

        with self.assertRaisesRegex(RuntimeError, "incomplete verified revision"):
            validate_competitor_panel(
                [
                    {
                        key: value
                        for key, value in competitor.items()
                        if key != "source_date"
                    }
                ],
                minimum=1,
                label="Panel",
                require_provenance=True,
            )
        with self.assertRaisesRegex(RuntimeError, "partial provenance as legacy"):
            validate_competitor_panel(
                [{**competitor, "provenance_status": "legacy-unversioned"}],
                minimum=1,
                label="Panel",
                require_provenance=True,
            )

        legacy = {
            key: value
            for key, value in competitor.items()
            if key not in {"source_version", "source_date"}
        }
        legacy["provenance_status"] = "legacy-unversioned"
        validate_competitor_panel(
            [legacy], minimum=1, label="Panel", require_provenance=True
        )

    def test_detail_path(self) -> None:
        stable_id = "arxiv:1"
        reading = {"stable_id": stable_id, "reading_depth": "full_text"}
        paper = {
            "id": "paper-1",
            "stable_id": stable_id,
            "record_kind": "paper",
            "reading_depth": "full_text",
            "full_reading_path": reading_public_path(stable_id, reading),
            "topics": [],
            "tricks": [],
        }
        validate_paper_routes({"papers": [paper]}, {stable_id: reading})

        missing_path = {**paper}
        del missing_path["full_reading_path"]
        with self.assertRaisesRegex(RuntimeError, "depth and detail path"):
            validate_paper_routes({"papers": [missing_path]})

        unsafe_path = {**paper, "full_reading_path": "/data/readings/../1.json"}
        with self.assertRaisesRegex(RuntimeError, "Unsafe or stale"):
            validate_paper_routes({"papers": [unsafe_path]})

    def test_legacy_reading(self) -> None:
        paper = {
            "id": "paper-1",
            "stable_id": "arxiv:1",
            "record_kind": "paper",
            "reading_depth": "abstract",
            "topics": [],
            "tricks": [],
            "full_reading": None,
        }
        with self.assertRaisesRegex(RuntimeError, "Legacy embedded reading"):
            validate_paper_routes({"papers": [paper]})

    def test_researched_brief(self) -> None:
        idea = {
            "id": "researched-idea",
            "origin": "cross-paper-reviewed",
            "feasibility": {"screening_estimate": False},
            "brief": {
                "status": "researched-draft",
                "method": ["Controlled experiment"],
                "evaluation": ["Primary metric"],
                "risks": ["Confound"],
                "first_week": ["Reproduce baseline"],
                "paper_ids": ["arxiv:1"],
                "experiment": {
                    "primary_hypothesis": "The intervention improves the outcome.",
                    "secondary_hypothesis": "The effect transfers.",
                    "domains": ["Registered domain"],
                    "baselines": ["Matched control"],
                    "ablations": ["Remove the intervention"],
                    "primary_outcome": "Registered held-out effect",
                    "decision_rule": "Reject when the registered effect is absent.",
                },
                "competitive_landscape": [
                    {
                        "canonical_id": f"arxiv:prior-{index}",
                        "title": f"Prior work {index}",
                        "url": f"https://arxiv.org/abs/prior-{index}",
                        "relationship": "direct baseline",
                        "difference": "The proposal adds a prospective intervention.",
                        "provenance_status": "version-verified",
                        "source_kind": "arxiv",
                        "source_version": f"arXiv:prior-{index}v1",
                        "source_date": "2026-08-01",
                        "checked_at": "2026-08-23",
                    }
                    for index in range(5)
                ],
                "novelty_assessment": "Narrow prospective claim",
                "confidence": 0.8,
            },
        }
        with self.assertRaisesRegex(RuntimeError, "multiple full-reading supports"):
            validate_researched_brief(idea, {"arxiv:1"})

        idea["brief"]["paper_ids"].append("arxiv:2")
        validate_researched_brief(idea, {"arxiv:1", "arxiv:2"})

        for field, invalid in (
            ("method", [False]),
            ("evaluation", [1]),
            ("risks", [""]),
            ("first_week", [{}]),
        ):
            original = idea["brief"][field]
            idea["brief"][field] = invalid
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeError, f"lacks {field}"):
                    validate_researched_brief(idea, {"arxiv:1", "arxiv:2"})
            idea["brief"][field] = original

        decision_rule = idea["brief"]["experiment"].pop("decision_rule")
        with self.assertRaisesRegex(RuntimeError, "experiment lacks decision_rule"):
            validate_researched_brief(idea, {"arxiv:1", "arxiv:2"})
        idea["brief"]["experiment"]["decision_rule"] = decision_rule

        competitor_url = idea["brief"]["competitive_landscape"][0]["url"]
        idea["brief"]["competitive_landscape"][0]["url"] = "https://example.com/summary"
        with self.assertRaisesRegex(RuntimeError, "non-primary URL"):
            validate_researched_brief(idea, {"arxiv:1", "arxiv:2"})
        idea["brief"]["competitive_landscape"][0]["url"] = competitor_url

        original_competitors = idea["brief"]["competitive_landscape"]
        idea["origin"] = "user-specified"
        idea["brief"]["paper_ids"] = ["arxiv:1"]
        idea["brief"]["competitive_landscape"] = [
            {
                **original_competitors[index % len(original_competitors)],
                "canonical_id": f"arxiv:external-{index}",
                "url": (
                    "https://example.com/summary"
                    if index == 0
                    else f"https://arxiv.org/abs/external-{index}"
                ),
            }
            for index in range(10)
        ]
        with self.assertRaisesRegex(RuntimeError, "non-primary URL"):
            validate_researched_brief(idea, {"arxiv:1"})

        idea["origin"] = "cross-paper-reviewed"
        idea["brief"]["paper_ids"] = ["arxiv:1", "arxiv:2"]
        idea["brief"]["competitive_landscape"] = original_competitors
        idea["brief"]["competitive_landscape"] = idea["brief"]["competitive_landscape"][
            :4
        ]
        with self.assertRaisesRegex(RuntimeError, "competitive review"):
            validate_researched_brief(idea, {"arxiv:1", "arxiv:2"})

    def test_fixed_rubric(self) -> None:
        idea = {
            "id": "idea-1",
            "origin": "cross-paper",
            "topic_ids": ["agents"],
            "repo_ids": [],
            "brief": {"status": "provisional"},
        }
        idea["feasibility"] = score_feasibility(idea)
        idea["feasibility"]["factors"][0]["max"] = 99
        with self.assertRaisesRegex(RuntimeError, "rubric factors drifted"):
            validate_feasibility(idea)

        idea["feasibility"] = score_feasibility(idea)
        idea["feasibility"]["factors"][0]["score"] = 1.41
        with self.assertRaisesRegex(RuntimeError, "factor exceeds"):
            validate_feasibility(idea)

    def test_feasibility_text(self) -> None:
        base = {
            "id": "idea-1",
            "origin": "cross-paper",
            "topic_ids": ["agents"],
            "repo_ids": [],
            "brief": {"status": "provisional"},
        }
        for field in ("version", "assumptions"):
            idea = {**base, "feasibility": score_feasibility(base)}
            idea["feasibility"][field] = " \t" if field == "version" else [" \t"]
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeError, "schema violation"):
                    validate_feasibility(idea)

    def test_lifecycle_values(self) -> None:
        idea = {
            "id": "idea-1",
            "origin": "cross-paper",
            "topic_ids": ["agents"],
            "repo_ids": [],
            "brief": {"status": "provisional"},
        }
        idea["feasibility"] = score_feasibility(idea)

        idea["origin"] = "mystery-source"
        with self.assertRaisesRegex(RuntimeError, "Unknown idea origin"):
            validate_feasibility(idea)

        idea["origin"] = "cross-paper"
        idea["brief"]["status"] = "finished"
        with self.assertRaisesRegex(RuntimeError, "Unknown brief status"):
            validate_feasibility(idea)

    def test_success_metrics(self) -> None:
        entry = valid_fulltext_entry()
        del entry["text_sha256"]
        with self.assertRaisesRegex(RuntimeError, "integrity metrics"):
            validate_fulltext_integrity([entry])

    def test_partial_metrics(self) -> None:
        entry = valid_fulltext_entry()
        entry["status"] = "partial_text"
        del entry["missing_text_pages"]
        with self.assertRaisesRegex(RuntimeError, "integrity metrics"):
            validate_fulltext_integrity([entry])

    def test_fulltext_status(self) -> None:
        unknown = valid_fulltext_entry()
        unknown["status"] = "banana"
        with self.assertRaisesRegex(RuntimeError, "Unknown extraction status"):
            validate_fulltext_integrity([unknown])

        duplicate = valid_fulltext_entry()
        with self.assertRaisesRegex(RuntimeError, "duplicate stable ID"):
            validate_fulltext_integrity([duplicate, duplicate.copy()])

    def test_source_routes(self) -> None:
        entry = valid_fulltext_entry()
        entry["pdf_url"] = "https://export.arxiv.org/pdf/1"
        records = [
            {
                "stable_id": "arxiv:1",
                "identifier_kind": "arxiv",
                "arxiv_id": "1",
            }
        ]

        validate_source_routes([entry], records)

        records[0]["pdf_url_override"] = "https://example.org/new.pdf"
        with self.assertRaisesRegex(RuntimeError, "route drifted"):
            validate_source_routes([entry], records)

    def test_fulltext_metrics(self) -> None:
        bad_hash = valid_fulltext_entry()
        bad_hash["text_sha256"] = "z" * 64
        with self.assertRaisesRegex(RuntimeError, "integrity metrics"):
            validate_fulltext_integrity([bad_hash])

        impossible_pages = valid_fulltext_entry()
        impossible_pages["pages_with_text"] = 10
        with self.assertRaisesRegex(RuntimeError, "quality metrics"):
            validate_fulltext_integrity([impossible_pages])

        invalid_ocr_pages = valid_fulltext_entry()
        invalid_ocr_pages["ocr_attempted_pages"] = [2, 2, 11]
        with self.assertRaisesRegex(RuntimeError, "OCR attempt metadata"):
            validate_fulltext_integrity([invalid_ocr_pages])

    def test_html_fulltext(self) -> None:
        entry = valid_fulltext_entry("openreview:abc_DEF")
        del entry["pdf_sha256"]
        entry.update(
            {
                "source_format": "html",
                "source_route": "source_override",
                "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
                "origin_url": "https://openreview.net/pdf?id=abc_DEF",
                "source_sha256": "c" * 64,
                "download_adapter": "scholar_html",
            }
        )

        validate_fulltext_integrity([entry])

        entry["pdf_sha256"] = "a" * 64
        with self.assertRaisesRegex(RuntimeError, "integrity metrics"):
            validate_fulltext_integrity([entry])

    def test_html_ocr(self) -> None:
        entry = valid_fulltext_entry("openreview:abc_DEF")
        del entry["pdf_sha256"]
        entry.update(
            {
                "source_format": "html",
                "source_route": "source_override",
                "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
                "origin_url": "https://openreview.net/pdf?id=abc_DEF",
                "source_sha256": "c" * 64,
                "download_adapter": "scholar_html",
                "ocr_attempted_pages": [10],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "OCR attempt metadata"):
            validate_fulltext_integrity([entry])

    def test_html_cache(self) -> None:
        def payload(page_count: int = 10, stable_id: str = "abc_DEF") -> bytes:
            pages = "".join(
                f"<table border=0 width=100%><b>Page {page}</b></table>"
                + ("reviewable source text " * 4)
                for page in range(1, page_count + 1)
            )
            return (
                f'<base href="https://openreview.net/forum?id={stable_id}">{pages}'
            ).encode()

        entry = valid_fulltext_entry("openreview:abc_DEF")
        del entry["pdf_sha256"]
        entry.update(
            {
                "source_format": "html",
                "source_route": "source_override",
                "source_url": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
                "origin_url": "https://openreview.net/pdf?id=abc_DEF",
                "source_sha256": hashlib.sha256(payload()).hexdigest(),
                "text_sha256": hashlib.sha256(
                    cache_text(payload()).encode("utf-8")
                ).hexdigest(),
                "download_adapter": "scholar_html",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "data/cache/html"
            cache.mkdir(parents=True)
            raw_path = cache / "nonexistent-test-fixture.html"
            raw_path.write_bytes(payload())
            with patch("readings.ROOT", root):
                validate_fulltext_integrity([entry])

                original_text_hash = entry["text_sha256"]
                entry["text_sha256"] = "b" * 64
                with self.assertRaisesRegex(RuntimeError, "extracted cache drifted"):
                    validate_fulltext_integrity([entry])
                entry["text_sha256"] = original_text_hash

                raw_path.write_bytes(payload() + b" ")
                with self.assertRaisesRegex(RuntimeError, "source cache drifted"):
                    validate_fulltext_integrity([entry])

                wrong = payload(stable_id="wrong")
                raw_path.write_bytes(wrong)
                entry["source_sha256"] = hashlib.sha256(wrong).hexdigest()
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    validate_fulltext_integrity([entry])

                shorter = payload(page_count=9)
                raw_path.write_bytes(shorter)
                entry["source_sha256"] = hashlib.sha256(shorter).hexdigest()
                with self.assertRaisesRegex(RuntimeError, "page count drifted"):
                    validate_fulltext_integrity([entry])

    def test_reading_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reading.json"
            validate_reading(path, valid_reading())

    def test_reading_text(self) -> None:
        cases = (
            (("question",), " \t"),
            (("key_findings", 0, "claim"), " \t"),
            (("key_findings", 0, "anchors", 0, "section"), " \t"),
            (("method", "core_idea"), " \t"),
            (("method", "assumptions"), [" \t"]),
            (("limitations",), [" \t"]),
            (("competitive_landscape", 0, "relationship"), " \t"),
            (("reviewer_notes",), " \t"),
        )

        for path, value in cases:
            reading = valid_reading()
            target = reading
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path):
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(RuntimeError, "schema violation"):
                        validate_reading(Path(directory) / "reading.json", reading)

    def test_html_reading(self) -> None:
        reading = valid_reading()
        reading["source_provenance"] = {
            "source_locator": "https://scholar.googleusercontent.com/scholar?q=cache:abc",
            "source_format": "html",
            "source_sha256": "c" * 64,
            "text_sha256": "b" * 64,
            "page_count": 8,
            "extracted_at": "2026-08-23T00:00:00+00:00",
            "review_pass": "primary-full-text-v1",
        }
        with tempfile.TemporaryDirectory() as directory:
            validate_reading(Path(directory) / "reading.json", reading)

            reading["source_provenance"]["pdf_sha256"] = "a" * 64
            with self.assertRaisesRegex(RuntimeError, "schema violation"):
                validate_reading(Path(directory) / "reading.json", reading)

    def test_anchor_missing(self) -> None:
        reading = valid_reading()
        reading["key_findings"][0]["anchors"] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reading.json"
            with self.assertRaisesRegex(RuntimeError, "schema violation"):
                validate_reading(path, reading)

    def test_anchor_range(self) -> None:
        reading = valid_reading()
        reading["key_findings"][0]["anchors"] = [{"page": 9, "section": "A"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reading.json"
            with self.assertRaisesRegex(RuntimeError, "exceeds the extracted source"):
                validate_reading(path, reading)
            with self.assertRaisesRegex(RuntimeError, "exceeds the extracted source"):
                validate_reading(path, reading, maximum_page=8)

    def test_anchor_content(self) -> None:
        reading = valid_reading()
        reading["key_findings"][0]["anchors"] = [{"page": 2, "section": "Figure"}]
        source_entry = {
            "pdf_url": "https://arxiv.org/pdf/1",
            "pdf_sha256": "a" * 64,
            "text_sha256": "b" * 64,
            "page_count": 8,
            "processed_at": "2026-08-23T00:00:00+00:00",
            "missing_text_pages": [2],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reading.json"
            with self.assertRaisesRegex(RuntimeError, "without usable extracted text"):
                validate_reading(path, reading, source_entry=source_entry)

    def test_source_drift(self) -> None:
        reading = valid_reading()
        source_entry = {
            "stable_id": "arxiv:1",
            "pdf_url": "https://arxiv.org/pdf/1",
            "pdf_sha256": "c" * 64,
            "text_sha256": "b" * 64,
            "page_count": 8,
            "processed_at": "2026-08-23T00:00:00+00:00",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reading.json"
            with self.assertRaisesRegex(RuntimeError, "source revision drifted"):
                validate_reading(path, reading, source_entry=source_entry)

    def test_competitor_identity(self) -> None:
        duplicate = valid_reading()
        duplicate["competitive_landscape"][1]["canonical_id"] = "arxiv:prior-0"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "duplicate records"):
                validate_reading(Path(directory) / "reading.json", duplicate)

        self_competitor = valid_reading()
        self_competitor["competitive_landscape"][0]["canonical_id"] = "arxiv:1"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "own competitor"):
                validate_reading(Path(directory) / "reading.json", self_competitor)

        non_primary = valid_reading()
        non_primary["competitive_landscape"][0]["url"] = "https://example.com/blog"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "non-primary URL"):
                validate_reading(Path(directory) / "reading.json", non_primary)

        official_neurips = valid_reading()
        official_neurips["competitive_landscape"][0]["url"] = (
            "https://proceedings.neurips.cc/paper_files/paper/2024/"
            "hash/example-Abstract-Conference.html"
        )
        with tempfile.TemporaryDirectory() as directory:
            validate_reading(Path(directory) / "reading.json", official_neurips)

        for url in (
            "https://papers.nips.cc/paper_files/paper/2024/hash/example.html",
            "https://www.jmlr.org/papers/v26/24-0065.html",
            "https://openaccess.thecvf.com/content_CVPR_2019/html/example.html",
        ):
            official_record = valid_reading()
            official_record["competitive_landscape"][0]["url"] = url
            with tempfile.TemporaryDirectory() as directory:
                validate_reading(Path(directory) / "reading.json", official_record)

    def test_progress_stale(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "full_readings"):
            validate_progress(
                {"updated_at": "old", "full_readings": 2},
                {"updated_at": "new", "full_readings": 3},
            )

    def test_queue_rebuild(self) -> None:
        records = [
            {"stable_id": "arxiv:1", "title": "One"},
            {"stable_id": "arxiv:2", "title": "Two"},
        ]
        fulltext_entries = [{"stable_id": "arxiv:1", "status": "full_text_ok"}]
        readings = {
            "arxiv:1": {
                "reading_depth": "full_text",
                "key_findings": [{"attribution": "author-reported"}],
                "novelty_assessment": {
                    "author_claim": "Claim",
                    "reviewer_inference": "Narrower claim",
                },
                "competitive_landscape": [{} for _ in range(5)],
            }
        }
        reading_queue = build_reading_queue(
            records, fulltext_entries, set(readings), batch_size=2
        )
        verification_queue = build_verification_queue(records, readings, batch_size=2)
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            (generated / "reading_queue.json").write_text(
                json.dumps(reading_queue), encoding="utf-8"
            )
            (generated / "verification_queue.json").write_text(
                json.dumps(verification_queue), encoding="utf-8"
            )
            validate_review_queues(generated, records, fulltext_entries, readings)

            reading_queue["paper_states"]["reviewed"] = 0
            (generated / "reading_queue.json").write_text(
                json.dumps(reading_queue), encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "Reading queue is stale"):
                validate_review_queues(generated, records, fulltext_entries, readings)

    def test_novelty_valid(self) -> None:
        reading = valid_reading()
        reading["novelty_assessment"] = {
            "author_claim": "Broad claim",
            "evidence": "Primary evidence",
            "reviewer_inference": "Narrow reviewer conclusion",
        }
        with tempfile.TemporaryDirectory() as directory:
            validate_reading(Path(directory) / "reading.json", reading)

    def test_verified_novelty(self) -> None:
        reading = valid_reading()
        reading["reading_depth"] = "verified"
        reading["source_provenance"]["review_pass"] = "secondary-verified-v1"
        reading["verification"] = {
            "reviewer_id": "reviewer-0123456789ab",
            "checked_at": "2026-08-23",
            "passage_check": "All cited passages independently checked.",
            "competitor_check": "All primary records independently checked.",
        }
        for finding in reading["key_findings"]:
            finding["attribution"] = "author-reported"
        for competitor in reading["competitive_landscape"]:
            competitor.update(
                {
                    "source_kind": "arxiv",
                    "checked_at": "2026-08-23",
                    "source_version": "v1",
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "novelty_assessment"):
                validate_reading(Path(directory) / "reading.json", reading)

    def test_second_pass(self) -> None:
        reading = valid_reading()
        reading["reading_depth"] = "verified"
        reading["novelty_assessment"] = {
            "author_claim": "Claim",
            "reviewer_inference": "Inference",
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "schema violation"):
                validate_reading(Path(directory) / "reading.json", reading)

    def test_fulltext_pass(self) -> None:
        reading = valid_reading()
        reading["source_provenance"]["review_pass"] = "secondary-verified-v1"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "schema violation"):
                validate_reading(Path(directory) / "reading.json", reading)


if __name__ == "__main__":
    unittest.main()
