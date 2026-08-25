from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from assign import build_reading_queue  # noqa: E402


class ReadingQueueTests(unittest.TestCase):
    def test_batch_partition(self) -> None:
        records = [
            {"stable_id": f"arxiv:{index}", "title": f"Paper {index}"}
            for index in range(1, 6)
        ]
        records.append(
            {
                "stable_id": "context:1",
                "title": "Context",
                "record_kind": "non_paper_context",
            }
        )
        records.append({**records[0], "title": "Duplicate collection entry"})
        fulltext = [
            {"stable_id": "arxiv:1", "status": "full_text_ok"},
            {"stable_id": "arxiv:2", "status": "full_text_ok"},
            {"stable_id": "arxiv:3", "status": "partial_text"},
            {"stable_id": "arxiv:4", "status": "full_text_ok"},
        ]

        queue = build_reading_queue(
            records,
            fulltext,
            {"arxiv:1"},
            batch_size=2,
        )

        self.assertEqual(queue["canonical_paper_count"], 5)
        self.assertEqual(queue["assignment_count"], 3)
        self.assertEqual(
            [assignment["id"] for assignment in queue["assignments"]],
            ["corpus-reading-0001", "corpus-reading-0002", "corpus-reading-0003"],
        )
        self.assertEqual(
            [assignment["status"] for assignment in queue["assignments"]],
            ["ready", "partially-ready", "awaiting-extraction"],
        )
        paper_ids = [
            paper["stable_id"]
            for assignment in queue["assignments"]
            for paper in assignment["papers"]
        ]
        self.assertEqual(len(paper_ids), len(set(paper_ids)))
        self.assertNotIn("context:1", paper_ids)

    def test_assignment_complete(self) -> None:
        records = [{"stable_id": "arxiv:1", "title": "Paper"}]

        queue = build_reading_queue(records, [], {"arxiv:1"}, batch_size=8)

        self.assertEqual(queue["assignments"][0]["status"], "complete")

    def test_batch_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            build_reading_queue([], [], set(), batch_size=0)


if __name__ == "__main__":
    unittest.main()
