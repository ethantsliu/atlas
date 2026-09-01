from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from titles import title_issue, valid_title  # noqa: E402


class TitleTests(unittest.TestCase):
    def test_curator_text(self) -> None:
        self.assertEqual(
            title_issue("READ THIS! THIS IS RELEVANT TO A PAPER"),
            "curator annotation",
        )
        self.assertEqual(title_issue("Q1: Why? Q2: How?"), "curator annotation")
        self.assertTrue(valid_title("q0: Primitives for Hyper-Epoch Pretraining"))
        self.assertEqual(
            title_issue("https://arxiv.org/abs/2401.00001"), "bare URL title"
        )

    def test_import_guard(self) -> None:
        self.assertTrue(valid_title("Read the Signs: A Learning Study", strict=True))
        self.assertFalse(
            valid_title("A Paper https://arxiv.org/abs/2401.00001", strict=True)
        )
        self.assertFalse(valid_title("---------------- A Paper", strict=True))


if __name__ == "__main__":
    unittest.main()
