from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from corpusbatch import token_delay  # noqa: E402


class BatchTests(unittest.TestCase):
    def test_token_delay(self) -> None:
        early = datetime(2026, 8, 30, 22, 0, tzinfo=timezone.utc)
        near = datetime(2026, 8, 30, 23, 25, tzinfo=timezone.utc)

        self.assertEqual(token_delay(early), 0)
        self.assertEqual(token_delay(near), 36 * 60)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            token_delay(datetime(2026, 8, 30, 23, 25))


if __name__ == "__main__":
    unittest.main()
