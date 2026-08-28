import json
import hashlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from reap import SAFE_CAP, point_plan, promo_plan  # noqa: E402


NOW = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)


def asset(identifier: int, name: str, created: str = "2026-08-20T00:00:00Z") -> dict:
    """Build one uploaded release asset."""
    return {
        "id": identifier,
        "name": name,
        "created_at": created,
        "state": "uploaded",
    }


class ReapTests(unittest.TestCase):
    def test_promo_age(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "index.json"
            ready = root / "cloud-ready.json"
            index.write_text(
                json.dumps(
                    {
                        "shards": [
                            {"path": "2026-07-0123456789abcdef.json.gz"},
                            {"path": "2026-08-fedcba9876543210.json.gz"},
                        ]
                    }
                )
            )
            ready.write_text(
                json.dumps(
                    {"index_sha256": hashlib.sha256(index.read_bytes()).hexdigest()}
                )
            )
            index_tag = hashlib.sha256(index.read_bytes()).hexdigest()[:16]
            ready_tag = hashlib.sha256(ready.read_bytes()).hexdigest()[:16]
            assets = [
                asset(1, "index.json"),
                asset(2, "cloud-ready.json"),
                asset(3, f"index-{index_tag}.json"),
                asset(4, f"ready-{ready_tag}.json"),
                asset(5, "2026-07-0123456789abcdef.json.gz"),
                asset(6, "2026-08-fedcba9876543210.json.gz"),
                asset(7, "2026-08-aaaaaaaaaaaaaaaa.json.gz"),
                asset(8, "index-bbbbbbbbbbbbbbbb.json", "2026-08-28T11:00:00Z"),
                asset(9, "notes.txt"),
            ]
            plan = promo_plan(assets, index, ready, NOW)
            self.assertEqual(plan["delete"], [7])
            self.assertEqual(plan["retained"], 8)

    def test_starter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pointer = Path(directory) / "pointer.json"
            part = "checkpoint-aabbccddeeff0011-0000-0011223344556677.part"
            current = "pointer-30-1-aaaaaaaaaaaaaaaa.json"
            pointer.write_text(json.dumps({"parts": [{"name": part}], "keep": [part]}))
            assets = [
                asset(1, part),
                asset(2, current),
                {**asset(3, "pointer-20-1-bbbbbbbbbbbbbbbb.json"), "state": "starter"},
            ]
            plan = point_plan(assets, pointer, current)
            self.assertEqual(plan["delete"], [3])

    def test_promo_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "index.json"
            ready = root / "cloud-ready.json"
            index.write_text(
                json.dumps({"shards": [{"path": "2026-08-aaaaaaaaaaaaaaaa.json.gz"}]})
            )
            ready.write_text(
                json.dumps(
                    {"index_sha256": hashlib.sha256(index.read_bytes()).hexdigest()}
                )
            )
            with self.assertRaisesRegex(
                ValueError, "Required release assets are missing"
            ):
                promo_plan([], index, ready, NOW)

    def test_point_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pointer = Path(directory) / "pointer.json"
            current_part = "checkpoint-aabbccddeeff0011-0000-0011223344556677.part"
            prior_part = "checkpoint-1122334455667788-0000-8899aabbccddeeff.part"
            pointer.write_text(
                json.dumps(
                    {
                        "parts": [{"name": current_part}],
                        "keep": sorted([current_part, prior_part]),
                    }
                )
            )
            assets = [
                asset(1, current_part),
                asset(2, prior_part),
                asset(3, "checkpoint-aaaaaaaaaaaaaaaa-0000-bbbbbbbbbbbbbbbb.part"),
                asset(4, "pointer-30-1-aaaaaaaaaaaaaaaa.json", "2026-08-28T11:00:00Z"),
                asset(5, "pointer-20-1-bbbbbbbbbbbbbbbb.json", "2026-08-27T11:00:00Z"),
                asset(6, "pointer-10-1-cccccccccccccccc.json"),
            ]
            plan = point_plan(assets, pointer, "pointer-30-1-aaaaaaaaaaaaaaaa.json")
            self.assertEqual(plan["delete"], [2, 3, 5, 6])
            self.assertEqual(plan["retained"], 2)

    def test_safe_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pointer = Path(directory) / "pointer.json"
            part = "checkpoint-aabbccddeeff0011-0000-0011223344556677.part"
            pointer.write_text(json.dumps({"parts": [{"name": part}], "keep": [part]}))
            assets = [asset(1, part), asset(2, "pointer-30-1-aaaaaaaaaaaaaaaa.json")]
            assets.extend(
                asset(index + 3, f"note-{index}.txt") for index in range(SAFE_CAP)
            )
            with self.assertRaisesRegex(RuntimeError, "after safe pruning"):
                point_plan(assets, pointer, "pointer-30-1-aaaaaaaaaaaaaaaa.json")

    def test_reserve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pointer = Path(directory) / "pointer.json"
            part = "checkpoint-aabbccddeeff0011-0000-0011223344556677.part"
            pointer.write_text(json.dumps({"parts": [{"name": part}]}))
            assets = [asset(1, part), asset(2, "pointer-30-1-aaaaaaaaaaaaaaaa.json")]
            with self.assertRaisesRegex(RuntimeError, "needs 901 assets"):
                point_plan(
                    assets,
                    pointer,
                    "pointer-30-1-aaaaaaaaaaaaaaaa.json",
                    SAFE_CAP - 1,
                )


if __name__ == "__main__":
    unittest.main()
