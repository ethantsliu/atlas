from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from ontology import TOPICS, TRICKS, phrase_hit, route  # noqa: E402


class OntologyRoutingTests(unittest.TestCase):
    def test_variance_noise(self) -> None:
        labels = {item["id"] for item in route("A strong baseline model", TRICKS)}
        self.assertNotIn("variance-control", labels)

    def test_theory_noise(self) -> None:
        labels = {item["id"] for item in route("Theory of mind in agents", TOPICS)}
        self.assertNotIn("learning-theory", labels)

    def test_phrase_boundaries(self) -> None:
        labels = {item["id"] for item in route("A chemical reagent study", TOPICS)}
        self.assertNotIn("agents", labels)

    def test_variance_route(self) -> None:
        labels = {
            item["id"]
            for item in route("We use a control variate for variance reduction", TRICKS)
        }
        self.assertIn("variance-control", labels)

    def test_agent_route(self) -> None:
        labels = {item["id"] for item in route("Language agents use tools", TOPICS)}
        self.assertIn("agents", labels)

    def test_tuning_route(self) -> None:
        labels = {item["id"] for item in route("Fine-tuning a policy", TOPICS)}
        self.assertIn("post-training", labels)

    def test_match_equivalence(self) -> None:
        cases = (
            ("agent", "agent"),
            ("an agent works", "agent"),
            ("reagent", "agent"),
            ("agentic", "agent"),
            ("agent-free", "agent"),
            ("agent_1", "agent"),
            ("map-elites", "map-elites"),
            ("(rlhf)", "rlhf"),
            ("caféagent", "agent"),
            ("agenté", "agent"),
        )
        for text, phrase in cases:
            with self.subTest(text=text, phrase=phrase):
                expected = re.search(
                    rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text
                )
                self.assertEqual(phrase_hit(text, phrase), expected is not None)


if __name__ == "__main__":
    unittest.main()
