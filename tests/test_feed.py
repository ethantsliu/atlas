import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from feed import (
    build_index,
    day_query,
    day_range,
    fetch_day,
    fetch_page,
    make_day,
    page_url,
    parse_page,
    raw_payload,
)
from rank import load_rules
from rescore import rescore_day


ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "data/source/feed.json")
DAY = date(2026, 8, 21)


def atom_page(total: int = 1) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
      <opensearch:totalResults>{total}</opensearch:totalResults>
      <entry>
        <id>https://arxiv.org/abs/2608.00001v1</id>
        <updated>2026-08-21T03:00:00Z</updated>
        <published>2026-08-21T03:00:00Z</published>
        <title> A daily learning paper </title>
        <summary> We introduce a machine learning method. </summary>
        <author><name>Ada Researcher</name></author>
        <category term="cs.LG" />
        <arxiv:primary_category term="cs.LG" />
        <arxiv:comment>12 pages</arxiv:comment>
      </entry>
    </feed>""".encode()


def make_intake() -> dict:
    _, papers = parse_page(atom_page())
    return {
        "source_total": 1,
        "fetched_count": 1,
        "unique_count": 1,
        "page_count": 1,
        "query": day_query(DAY),
        "papers": papers,
    }


class FeedTests(unittest.TestCase):
    @patch("feed.time.sleep")
    @patch("feed.fetch_once")
    def test_transient_retry(self, fetch_once, sleep) -> None:
        error = HTTPError("https://export.arxiv.org", 503, "busy", {}, None)
        fetch_once.side_effect = [error, (1, [{"id": "2608.00001"}])]

        total, papers = fetch_page(date(2026, 8, 21), 0, 500)

        self.assertEqual(total, 1)
        self.assertEqual(papers[0]["id"], "2608.00001")
        sleep.assert_called_once_with(3.1)

    @patch("feed.time.sleep")
    @patch("feed.fetch_once")
    def test_final_retry(self, fetch_once, sleep) -> None:
        error = HTTPError("https://export.arxiv.org", 404, "missing", {}, None)
        fetch_once.side_effect = error

        with self.assertRaises(HTTPError):
            fetch_page(date(2026, 8, 21), 0, 500)

        sleep.assert_not_called()

    def test_parse_page(self) -> None:
        total, papers = parse_page(atom_page())

        self.assertEqual(total, 1)
        self.assertEqual(papers[0]["id"], "2608.00001")
        self.assertEqual(papers[0]["authors"], ["Ada Researcher"])
        self.assertEqual(papers[0]["categories"], ["cs.LG"])
        self.assertEqual(papers[0]["title"], "A daily learning paper")

    def test_query_window(self) -> None:
        query = day_query(DAY)
        url = page_url(DAY, 200, 500)

        self.assertEqual(query, "submittedDate:[202608210000 TO 202608212359]")
        self.assertIn("start=200", url)
        self.assertIn("max_results=500", url)
        self.assertIn("sortBy=submittedDate", url)

    def test_day_range(self) -> None:
        self.assertEqual(
            day_range(DAY, 3),
            [date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21)],
        )

    @patch("feed.time.sleep")
    @patch("feed.fetch_page")
    def test_fetch_complete(self, fetch, sleep) -> None:
        first = {"id": "1", "title": "First"}
        second = {"id": "2", "title": "Second"}
        fetch.side_effect = [(2, [first]), (2, [second])]

        intake = fetch_day(DAY, size=1, delay=3.1)

        self.assertEqual(intake["source_total"], 2)
        self.assertEqual(intake["fetched_count"], 2)
        self.assertEqual(intake["page_count"], 2)
        sleep.assert_called_once_with(3.1)

    @patch("feed.fetch_page", return_value=(2, []))
    def test_partial_fetch(self, _fetch) -> None:
        with self.assertRaisesRegex(RuntimeError, "ended before"):
            fetch_day(DAY)

    def test_public_retention(self) -> None:
        intake = make_intake()
        intake["papers"][0]["comment"] = "Contact author@example.edu"
        intake["papers"][0]["authors"] = ["Ada <ada@example.edu>"]
        payload = make_day(DAY, intake, RULES, shortlist=1)

        self.assertTrue(payload["source"]["complete"])
        self.assertEqual(payload["relevant_count"], 1)
        self.assertEqual(payload["shortlist_ids"], ["2608.00001"])
        self.assertEqual(len(payload["papers"]), payload["relevant_count"])
        self.assertEqual(payload["papers"][0]["comment"], "")
        self.assertEqual(payload["papers"][0]["authors"], ["Ada"])

    def test_raw_auditable(self) -> None:
        intake = make_intake()
        intake["papers"][0]["comment"] = "Questions: author@example.edu"
        decoded = json.loads(gzip.decompress(raw_payload(DAY, intake)))

        self.assertEqual(decoded["date"], DAY.isoformat())
        self.assertEqual(decoded["source_total"], 1)
        self.assertEqual(len(decoded["papers"]), 1)
        self.assertEqual(decoded["papers"][0]["comment"], "Questions")

    def test_index_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for day in ("2026-08-20", "2026-08-21"):
                payload = make_day(date.fromisoformat(day), make_intake(), RULES, 1)
                (root / f"{day}.json").write_text(json.dumps(payload), encoding="utf-8")

            index = build_index(root)

        self.assertEqual(
            [item["date"] for item in index["days"]],
            ["2026-08-21", "2026-08-20"],
        )

    def test_rescore_raw(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            public = root / "public"
            public.mkdir()
            day_path = root / f"{DAY.isoformat()}.json"
            raw_path = root / f"{DAY.isoformat()}.json.gz"
            payload = make_day(DAY, make_intake(), {**RULES, "version": "old"}, 1)
            day_path.write_text(json.dumps(payload), encoding="utf-8")
            raw_path.write_bytes(raw_payload(DAY, make_intake()))

            rescored = rescore_day(day_path, raw_path, public, RULES)

            self.assertEqual(rescored["policy_version"], RULES["version"])
            self.assertEqual(rescored["generated_at"], payload["generated_at"])
            self.assertEqual(
                (public / day_path.name).read_bytes(), day_path.read_bytes()
            )


if __name__ == "__main__":
    unittest.main()
