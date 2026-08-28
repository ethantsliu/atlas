from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from corpus import plan_run, read_cursor, write_cursor  # noqa: E402
from harvest import run_harvest, stage_path  # noqa: E402
from sweep import attach_span, harvest_span, year_span  # noqa: E402


@dataclass(frozen=True)
class TestPage:
    records: tuple[dict, ...]
    token: str | None
    response_date: str
    expires: str | None = None
    cursor: int | None = None
    total: int | None = None


def record(identifier: str, stamp: str) -> dict:
    """Build one minimal deleted record for transport tests."""
    return {"id": identifier, "datestamp": stamp, "deleted": True}


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def pages(self, start=None, end=None, token=None):
        self.calls.append({"start": start, "end": end, "token": token})
        year = int(start[:4])
        yield TestPage(
            (record(f"{year}.00001", start),),
            None,
            f"2026-08-27T00:{year - 2000:02d}:00Z",
            cursor=0,
            total=1,
        )


def seed_cursor(root: Path) -> None:
    """Create the clean canonical cursor immediately after 2018."""
    write_cursor(
        root,
        {
            "schema_version": 1,
            "watermark": "2026-08-27T00:18:00Z",
            "active": None,
            "last_generation": "history-2018",
            "pending": [],
            "merged": [],
            "history": {
                "next_year": 2019,
                "through_year": 2020,
                "complete": False,
            },
        },
    )


class SweepTests(unittest.TestCase):
    def test_year_span(self) -> None:
        through = date(2020, 8, 27)
        self.assertEqual(
            year_span(2019, 2020, through),
            [
                (2019, "2019-01-01", "2019-12-31"),
                (2020, "2020-01-01", "2020-08-27"),
            ],
        )
        with self.assertRaisesRegex(ValueError, "range"):
            year_span(2020, 2021, through)

    def test_serial_harvest(self) -> None:
        client = FakeClient()
        through = date(2020, 8, 27)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = harvest_span(root, 2019, 2020, through, client)

        self.assertEqual(result["records"], 2)
        self.assertEqual(
            client.calls,
            [
                {"start": "2019-01-01", "end": "2019-12-31", "token": None},
                {"start": "2020-01-01", "end": "2020-08-27", "token": None},
            ],
        )

    def test_harvest_resume(self) -> None:
        through = date(2020, 8, 27)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_harvest(
                root,
                "history-2019",
                FakeClient(),
                start="2019-01-01",
                end="2019-12-31",
            )
            client = FakeClient()
            result = harvest_span(root, 2019, 2020, through, client)

        self.assertEqual(result["generations"], ["history-2019", "history-2020"])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["start"], "2020-01-01")

    def test_attach(self) -> None:
        through = date(2020, 8, 27)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "sweep"
            target = base / "corpus"
            harvest_span(source, 2019, 2020, through, FakeClient())
            seed_cursor(target)
            archive = target / "archive"
            archive.mkdir(parents=True)
            marker = archive / "unchanged.txt"
            marker.write_text("archive bytes\n", encoding="utf-8")

            result = attach_span(source, target, 2019, 2020, through)
            cursor = read_cursor(target)

            self.assertEqual(marker.read_text(encoding="utf-8"), "archive bytes\n")
            self.assertEqual(result["copied"], ["history-2019", "history-2020"])
            self.assertEqual(cursor["pending"], ["history-2019", "history-2020"])
            self.assertEqual(cursor["merged"], [])
            self.assertIsNone(cursor["active"])
            self.assertEqual(cursor["last_generation"], "history-2020")
            self.assertEqual(cursor["history"]["next_year"], 2021)
            self.assertTrue(cursor["history"]["complete"])
            self.assertEqual(cursor["coverage_through_day"], "2020-08-27")
            self.assertEqual(cursor["watermark"], "2020-08-27T00:00:00Z")
            self.assertTrue(stage_path(target, "history-2019").is_dir())

    def test_overlap(self) -> None:
        through = date(2020, 8, 27)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "sweep"
            target = base / "corpus"
            harvest_span(source, 2019, 2020, through, FakeClient())
            seed_cursor(target)
            attach_span(source, target, 2019, 2020, through)
            cursor = read_cursor(target)
            write_cursor(target, {**cursor, "pending": [], "merged": []})

            _cursor, _generation, start, end = plan_run(
                target,
                datetime(2020, 8, 29, tzinfo=timezone.utc),
            )

            self.assertEqual(start, "2020-08-27")
            self.assertIsNone(end)

    def test_attach_collision(self) -> None:
        through = date(2020, 8, 27)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "sweep"
            target = base / "corpus"
            harvest_span(source, 2019, 2020, through, FakeClient())
            seed_cursor(target)
            collision = stage_path(target, "history-2020")
            collision.mkdir(parents=True)
            (collision / "state.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                attach_span(source, target, 2019, 2020, through)

            self.assertEqual(read_cursor(target)["pending"], [])
            self.assertFalse(stage_path(target, "history-2019").exists())

    def test_attach_query(self) -> None:
        through = date(2020, 8, 27)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "sweep"
            target = base / "corpus"
            harvest_span(source, 2019, 2020, through, FakeClient())
            seed_cursor(target)
            state = stage_path(source, "history-2020") / "state.json"
            payload = json.loads(state.read_text(encoding="utf-8"))
            payload["query"]["until"] = "2020-08-26"
            state.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ValueError):
                attach_span(source, target, 2019, 2020, through)


if __name__ == "__main__":
    unittest.main()
