from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from discoverypack import check_browser  # noqa: E402


class DiscoveryBrowserPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "web/public/data/discovery.json"
        cls.queue = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_provisional(self) -> None:
        self.assertIs(check_browser(self.queue), self.queue)
        self.assertEqual(self.queue["count"], 48)
        self.assertEqual(
            {row["review_status"] for row in self.queue["candidates"]},
            {"unreviewed"},
        )
        self.assertFalse(self.queue["review_gate"]["automatic_promotion"])
        self.assertIn("not screened briefs", self.queue["notice"])

    def test_tampering(self) -> None:
        promoted = copy.deepcopy(self.queue)
        promoted["candidates"][0]["review_status"] = "reviewed"
        with self.assertRaisesRegex(ValueError, "status"):
            check_browser(promoted)

        stale = copy.deepcopy(self.queue)
        stale["count"] -= 1
        with self.assertRaisesRegex(ValueError, "count"):
            check_browser(stale)

    def test_provenance(self) -> None:
        tampered = copy.deepcopy(self.queue)
        tampered["source"]["artifact_sha256"] = "missing"
        with self.assertRaisesRegex(ValueError, "artifact_sha256"):
            check_browser(tampered)


if __name__ == "__main__":
    unittest.main()
