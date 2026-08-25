from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from ontology import TOPICS, TRICKS, route  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
