from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from atlas import READINGS_DIR as ATLAS_READINGS_DIR  # noqa: E402
from related import (  # noqa: E402
    READINGS_DIR as RELATED_WORK_READINGS_DIR,
)
from paths import REVIEWED_READINGS_DIR  # noqa: E402
from lineage import READINGS_DIR as PROVENANCE_READINGS_DIR  # noqa: E402
from validate import READINGS_DIR as VALIDATION_READINGS_DIR  # noqa: E402


class ReviewedDataBoundaryTests(unittest.TestCase):
    def test_source_namespace(self) -> None:
        expected = ROOT / "data/reviewed/readings"
        generated = ROOT / "data/generated"

        self.assertTrue(expected.is_dir())
        self.assertFalse(expected.is_symlink())
        self.assertFalse((generated / "readings").exists())
        self.assertNotIn(generated.resolve(), expected.resolve().parents)
        self.assertEqual(REVIEWED_READINGS_DIR, expected)

    def test_consumer_paths(self) -> None:
        expected = ROOT / "data/reviewed/readings"

        self.assertEqual(ATLAS_READINGS_DIR, expected)
        self.assertEqual(RELATED_WORK_READINGS_DIR, expected)
        self.assertEqual(PROVENANCE_READINGS_DIR, expected)
        self.assertEqual(VALIDATION_READINGS_DIR, expected)


if __name__ == "__main__":
    unittest.main()
