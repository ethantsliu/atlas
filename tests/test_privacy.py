"""Adversarial privacy checks for automatically synthesized ideas."""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from briefs import validate_idea_boundary  # noqa: E402
from ideas import build_provisional_ideas  # noqa: E402


def candidate() -> dict:
    papers = [
        {
            "id": f"paper-{index}",
            "stable_id": f"arxiv:2401.0000{index}",
            "reading_depth": "abstract",
            "topics": [{"id": "agents"}],
            "tricks": [{"id": "retrieval-and-memory"}],
        }
        for index in (1, 2)
    ]
    return build_provisional_ideas(papers)[0]


class IdeaBoundaryTests(unittest.TestCase):
    def test_current_atlas(self) -> None:
        atlas = json.loads((ROOT / "data/generated/atlas.json").read_text())

        for idea in atlas["ideas"]:
            validate_idea_boundary(idea)

    def test_private_fields(self) -> None:
        for field in ("raw_prompt", "private_context"):
            with self.subTest(field=field):
                idea = candidate()
                idea[field] = "internal generation detail"
                with self.assertRaisesRegex(RuntimeError, "top-level fields"):
                    validate_idea_boundary(idea)

    def test_unsafe_text(self) -> None:
        unsafe = (
            "/Users/alice/private/project",
            "file:///tmp/private.txt",
            "author@example.org",
            "@private_handle",
            "https://twitter.com/private_handle",
            "https://linkedin.com/in/private-handle",
            "left\u202eright",
            "zero\u200bwidth",
            "line\nbreak",
        )
        for text in unsafe:
            with self.subTest(text=repr(text)):
                idea = candidate()
                idea["brief"]["title"] = text
                with self.assertRaisesRegex(RuntimeError, "unsafe text"):
                    validate_idea_boundary(idea)

    def test_reviewed_text(self) -> None:
        for origin in ("cross-paper-reviewed", "user-specified"):
            with self.subTest(origin=origin):
                idea = deepcopy(candidate())
                idea["origin"] = origin
                idea["brief"]["title"] = "Archived reviewer note: author@example.org"
                with self.assertRaisesRegex(RuntimeError, "unsafe text"):
                    validate_idea_boundary(idea)

    def test_synthesis_lifecycle(self) -> None:
        changes = (
            ("status", "researched-draft"),
            ("screening", False),
            ("novelty", "Model-generated novelty claim"),
            ("landscape", []),
        )
        for field, value in changes:
            with self.subTest(field=field):
                idea = candidate()
                if field == "status":
                    idea["brief"]["status"] = value
                elif field == "screening":
                    idea["feasibility"]["screening_estimate"] = value
                elif field == "novelty":
                    idea["brief"]["novelty_assessment"] = value
                else:
                    idea["brief"]["competitive_landscape"] = value
                with self.assertRaises(RuntimeError):
                    validate_idea_boundary(idea)

    def test_researched_origin(self) -> None:
        for origin in ("cross-paper-reviewed", "user-specified"):
            with self.subTest(origin=origin):
                idea = candidate()
                idea["origin"] = origin
                idea["brief"]["status"] = "researched-draft"
                validate_idea_boundary(idea)

        idea = candidate()
        idea["origin"] = "unknown"
        idea["brief"]["status"] = "researched-draft"
        with self.assertRaisesRegex(RuntimeError, "reviewed origin"):
            validate_idea_boundary(idea)


if __name__ == "__main__":
    unittest.main()
