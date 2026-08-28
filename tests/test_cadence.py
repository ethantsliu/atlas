from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SWEEP = ROOT / ".github/workflows/sweep.yml"
CLOUD = ROOT / ".github/workflows/cloudall.yml"


class SweepPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sweep = SWEEP.read_text(encoding="utf-8")

    def test_oai_serial(self) -> None:
        jobs = self.sweep.split("\njobs:\n", 1)[1]
        job_ids = re.findall(r"^  [a-z][a-z0-9_-]*:\s*$", jobs, re.MULTILINE)
        self.assertIn("  harvest:", job_ids)
        self.assertEqual(self.sweep.count("pipeline/sweep.py harvest"), 1)
        self.assertIn("group: arxiv-oai-corpus", self.sweep)
        self.assertIn("cancel-in-progress: false", self.sweep)
        harvest = jobs.split("  harvest:\n", 1)[1].split("\n  promote:\n", 1)[0]
        for parallel in ("strategy:", "matrix:", "max-parallel:", "xargs -P"):
            self.assertNotIn(parallel, harvest)

    def test_history_stage(self) -> None:
        self.assertIn("2019", self.sweep)
        self.assertIn("2026", self.sweep)
        self.assertIn("actions/upload-artifact@v4", self.sweep)
        self.assertRegex(self.sweep, r"retention-days:\s*[1-9][0-9]*")

    def test_cloud_parallel(self) -> None:
        cloud = CLOUD.read_text(encoding="utf-8")
        for required in ("strategy:", "matrix:", "max-parallel: 20"):
            self.assertIn(required, cloud)


if __name__ == "__main__":
    unittest.main()
