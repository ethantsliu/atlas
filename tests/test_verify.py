from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from verify import (  # noqa: E402
    build_verification_queue,
    review_state,
)


def reading(
    *,
    depth: str = "full_text",
    structured: bool = True,
    attributed: bool = True,
    competitors: int = 5,
) -> dict:
    return {
        "reading_depth": depth,
        "key_findings": [{"attribution": "author-reported" if attributed else None}],
        "novelty_assessment": (
            {"author_claim": "Claim", "reviewer_inference": "Inference"}
            if structured
            else "Legacy novelty note"
        ),
        "competitive_landscape": [{} for _ in range(competitors)],
    }


class VerificationQueueTests(unittest.TestCase):
    def test_review_partition(self) -> None:
        records = [
            {"stable_id": f"arxiv:{index}", "title": f"Paper {index}"}
            for index in range(1, 7)
        ]
        records.extend(
            [
                {
                    "stable_id": "context:1",
                    "title": "Context",
                    "record_kind": "non_paper_context",
                },
                {**records[0], "title": "Duplicate collection entry"},
            ]
        )
        readings = {
            "arxiv:1": reading(structured=False, attributed=False, competitors=3),
            "arxiv:2": reading(),
            "arxiv:3": reading(depth="verified"),
            "arxiv:5": reading(),
        }

        queue = build_verification_queue(records, readings, batch_size=2)

        self.assertEqual(queue["canonical_paper_count"], 6)
        self.assertEqual(
            [assignment["id"] for assignment in queue["assignments"]],
            [
                "corpus-verification-0001",
                "corpus-verification-0002",
                "corpus-verification-0003",
            ],
        )
        self.assertEqual(
            [assignment["status"] for assignment in queue["assignments"]],
            ["ready", "awaiting-reading", "partially-ready"],
        )
        self.assertEqual(
            queue["paper_states"],
            {
                "unread": 2,
                "needs-structural-upgrade": 1,
                "needs-second-review": 2,
                "verified": 1,
            },
        )

    def test_thin_panel(self) -> None:
        state, reasons = review_state(reading(depth="verified", competitors=4))

        self.assertEqual(state, "needs-second-review")
        self.assertEqual(reasons, ["thin-competitor-panel"])

    def test_assignment_complete(self) -> None:
        records = [{"stable_id": "arxiv:1", "title": "Paper"}]

        queue = build_verification_queue(
            records,
            {"arxiv:1": reading(depth="verified")},
            batch_size=8,
        )

        self.assertEqual(queue["assignments"][0]["status"], "complete")

    def test_batch_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            build_verification_queue([], {}, batch_size=0)


if __name__ == "__main__":
    unittest.main()
