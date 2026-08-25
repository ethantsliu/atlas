import json
from pathlib import Path
import tempfile
import unittest

from claims import claim_ids, release, reserve


class ClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.claims = root / "claims"
        self.readings = root / "readings"
        self.readings.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_atomic_reserve(self) -> None:
        path = reserve("arxiv:2201.00001", "agent-a", self.claims, self.readings)
        self.assertEqual(path.name, "arxiv_2201.00001.json")
        self.assertEqual(claim_ids(self.claims), {"arxiv:2201.00001"})
        with self.assertRaisesRegex(RuntimeError, "already claimed"):
            reserve("2201.00001", "agent-b", self.claims, self.readings)

    def test_legacy_block(self) -> None:
        self.claims.mkdir()
        (self.claims / "2201.00001").write_text("agent-a\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "already claimed"):
            reserve("arxiv:2201.00001", "agent-b", self.claims, self.readings)

    def test_final_block(self) -> None:
        payload = {"stable_id": "arxiv:2201.00001"}
        (self.readings / "paper.json").write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            reserve("arxiv:2201.00001", "agent-a", self.claims, self.readings)

    def test_release_owner(self) -> None:
        reserve("arxiv:2201.00001", "agent-a", self.claims, self.readings)
        self.assertEqual(release("2201.00001", "agent-b", self.claims), 0)
        self.assertEqual(release("2201.00001", "agent-a", self.claims), 1)
        self.assertEqual(claim_ids(self.claims), set())


if __name__ == "__main__":
    unittest.main()
