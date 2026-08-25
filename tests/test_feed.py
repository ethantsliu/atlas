import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from feed import (
    build_index,
    day_query,
    day_range,
    fetch_day,
    make_day,
    page_url,
    parse_page,
    raw_payload,
)
from rank import load_rules


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
        payload = make_day(DAY, intake, RULES, shortlist=1)

        self.assertTrue(payload["source"]["complete"])
        self.assertEqual(payload["relevant_count"], 1)
        self.assertEqual(payload["shortlist_ids"], ["2608.00001"])
        self.assertEqual(len(payload["papers"]), payload["relevant_count"])

    def test_raw_auditable(self) -> None:
        decoded = json.loads(gzip.decompress(raw_payload(DAY, make_intake())))

        self.assertEqual(decoded["date"], DAY.isoformat())
        self.assertEqual(decoded["source_total"], 1)
        self.assertEqual(len(decoded["papers"]), 1)

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


if __name__ == "__main__":
    unittest.main()
