from __future__ import annotations

import io
import sys
import unittest
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from oai import (  # noqa: E402
    EARLIEST,
    PAGE_LIMIT,
    RECORD_FIELDS,
    OaiClient,
    OaiError,
    build_url,
    parse_identity,
    parse_page,
    post_request,
    token_expired,
)

IDENTIFY = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <responseDate>2026-01-01T00:00:00Z</responseDate>
  <Identify>
    <repositoryName>arXiv</repositoryName>
    <baseURL>https://oaipmh.arxiv.org/oai</baseURL>
    <protocolVersion>2.0</protocolVersion>
    <adminEmail>help@arxiv.org</adminEmail>
    <earliestDatestamp>2005-09-16</earliestDatestamp>
    <deletedRecord>persistent</deletedRecord>
    <granularity>YYYY-MM-DD</granularity>
  </Identify>
</OAI-PMH>"""

PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <responseDate>2026-01-01T00:00:00Z</responseDate>
  <ListRecords>
    <record>
      <header>
        <identifier>oai:arXiv.org:2401.00001</identifier>
        <datestamp>2024-02-03</datestamp>
        <setSpec>physics:cs</setSpec>
      </header>
      <metadata>
        <arXiv xmlns="http://arxiv.org/OAI/arXiv/">
          <id>2401.00001</id>
          <created>2024-01-01</created>
          <updated>2024-02-02</updated>
          <authors>
            <author><keyname>Lovelace</keyname><forenames>Ada</forenames></author>
            <author><keyname>Hopper</keyname><forenames>Grace</forenames><suffix>Jr.</suffix></author>
          </authors>
          <title> A semantic\n atlas </title>
          <categories>cs.LG cs.AI stat.ML</categories>
          <comments>12 pages</comments>
          <doi>10.1/example</doi>
          <abstract> Maps many papers. </abstract>
        </arXiv>
      </metadata>
    </record>
    <record>
      <header status="deleted">
        <identifier>oai:arXiv.org:hep-th/9912345</identifier>
        <datestamp>2020-01-01</datestamp>
      </header>
    </record>
    <resumptionToken cursor="0" completeListSize="1234"
      expirationDate="2099-01-02T00:00:00Z">  next \n token  </resumptionToken>
  </ListRecords>
</OAI-PMH>"""

RAW_PAGE = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords><record><header>
    <identifier>oai:arXiv.org:hep-th/9901001</identifier><datestamp>2005-09-16</datestamp>
  </header><metadata><arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/">
    <id>hep-th/9901001</id><submitter>submitter@example.org</submitter>
    <version version="v1"><date>Fri, 1 Jan 1999</date><size>10kb</size><source_type>TeX</source_type></version>
    <version version="v2"><date>Mon, 4 Jan 1999</date><size>12kb</size><source_type>TeX</source_type></version>
    <title>Raw title</title><authors>Doe, J. and Roe, R.</authors>
    <categories>hep-th math-ph</categories><abstract>Raw abstract</abstract>
  </arXivRaw></metadata></record><resumptionToken />
  </ListRecords></OAI-PMH>"""

DONE = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords><record><header status="deleted"><identifier>oai:arXiv.org:2401.00002</identifier>
  <datestamp>2024-01-02</datestamp></header></record></ListRecords>
</OAI-PMH>"""

PRIVATE_PAGE = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListRecords><record><header><identifier>oai:arXiv.org:2401.00003</identifier>
  <datestamp>2024-01-03</datestamp></header><metadata>
  <arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>2401.00003</id>
  <created>2024-01-01</created><title>Left&#x202E;right</title>
  <authors><author><keyname>Researcher</keyname></author></authors>
  <categories>cs.LG</categories><comments>owner@localhost private note</comments>
  <submitter>owner@localhost</submitter><abstract>Public abstract</abstract>
  </arXiv></metadata></record></ListRecords></OAI-PMH>"""


class OaiParseTests(unittest.TestCase):
    def test_identity(self) -> None:
        identity = parse_identity(IDENTIFY)

        self.assertEqual(identity.repository, "arXiv")
        self.assertEqual(identity.base, "https://oaipmh.arxiv.org/oai")
        self.assertEqual(identity.earliest, EARLIEST)
        self.assertEqual(identity.granularity, "YYYY-MM-DD")
        self.assertEqual(identity.deletions, "persistent")

    def test_policy(self) -> None:
        changes = (
            (b">arXiv</repositoryName>", b">mirror</repositoryName>"),
            (
                b">https://oaipmh.arxiv.org/oai</baseURL>",
                b">https://example.org/oai</baseURL>",
            ),
            (b">2005-09-16</earliestDatestamp>", b">2005-09-15</earliestDatestamp>"),
            (b">persistent</deletedRecord>", b">transient</deletedRecord>"),
            (b">YYYY-MM-DD</granularity>", b">YYYY-MM-DDThh:mm:ssZ</granularity>"),
        )
        for current, changed in changes:
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "policy changed"):
                    parse_identity(IDENTIFY.replace(current, changed))

    def test_page(self) -> None:
        page = parse_page(PAGE)

        self.assertEqual(page.token, "next \n token")
        self.assertEqual(page.cursor, 0)
        self.assertEqual(page.total, 1234)
        self.assertEqual(page.response_date, "2026-01-01T00:00:00Z")
        paper, deleted = page.records
        self.assertEqual(paper["id"], "2401.00001")
        self.assertEqual(paper["title"], "A semantic atlas")
        self.assertEqual(paper["authors"], ["Ada Lovelace", "Grace Hopper Jr."])
        self.assertEqual(paper["categories"], ["cs.LG", "cs.AI", "stat.ML"])
        self.assertEqual(paper["published"], "2024-01-01")
        self.assertEqual(paper["updated"], "2024-02-02")
        self.assertEqual(set(paper), RECORD_FIELDS)
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["id"], "hep-th/9912345")
        self.assertEqual(set(deleted), {"id", "datestamp", "deleted"})
        self.assertNotIn("title", deleted)

    def test_bad_counts(self) -> None:
        for field in (b'cursor="bad"', b'completeListSize="-1"'):
            with self.subTest(field=field):
                source = PAGE.replace(b'cursor="0"', field)
                if field.startswith(b"complete"):
                    source = PAGE.replace(b'completeListSize="1234"', field)
                with self.assertRaisesRegex(ValueError, "invalid"):
                    parse_page(source)

    def test_raw(self) -> None:
        paper = parse_page(RAW_PAGE).records[0]

        self.assertEqual(paper["authors"], ["Doe, J.", "Roe, R."])
        self.assertEqual(paper["published"], "1999-01-01")
        self.assertEqual(paper["updated"], "1999-01-04")
        self.assertTrue(
            {
                "submitter",
                "authors_raw",
                "source_type",
                "size",
                "version_dates",
            }.isdisjoint(paper)
        )
        self.assertIsNone(parse_page(RAW_PAGE).token)

    def test_raw_date(self) -> None:
        offset = RAW_PAGE.replace(
            b"Fri, 1 Jan 1999", b"Thu, 31 Dec 1998 23:30:00 -0200"
        )
        self.assertEqual(parse_page(offset).records[0]["published"], "1999-01-01")

        malformed = RAW_PAGE.replace(b"Mon, 4 Jan 1999", b"not a date")
        with self.assertRaisesRegex(ValueError, "invalid date"):
            parse_page(malformed)

    def test_private_fields(self) -> None:
        paper = parse_page(PRIVATE_PAGE).records[0]

        self.assertEqual(paper["title"], "Leftright")
        self.assertNotIn("comment", paper)
        self.assertNotIn("submitter", paper)
        self.assertNotIn("owner@localhost", repr(paper))

    def test_id_guard(self) -> None:
        deleted = """<OAI-PMH><ListRecords><record><header status="deleted">
          <identifier>{}</identifier><datestamp>2024-01-01</datestamp>
          </header></record></ListRecords></OAI-PMH>"""
        bad_headers = (
            "file:///tmp/paper",
            "oai:arXiv.org:private/9901001",
            "oai:arXiv.org:2413.00001",
            "oai:arXiv.org:2401.\u202e00001",
            "oai:other:2401.00001",
        )
        for identifier in bad_headers:
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(ValueError, "identifier"):
                    parse_page(deleted.format(identifier))

        active = PRIVATE_PAGE.decode().replace(
            "<id>2401.00003</id>", "<id>owner@localhost</id>"
        )
        with self.assertRaisesRegex(ValueError, "identifier"):
            parse_page(active)

        mismatch = PRIVATE_PAGE.decode().replace(
            "<id>2401.00003</id>", "<id>2401.00004</id>"
        )
        with self.assertRaisesRegex(ValueError, "do not match"):
            parse_page(mismatch)

    def test_error(self) -> None:
        source = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <error code="badResumptionToken">expired</error></OAI-PMH>"""
        with self.assertRaisesRegex(OaiError, "badResumptionToken: expired"):
            parse_page(source)

    def test_no_records(self) -> None:
        source = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
          <responseDate>2026-01-03T00:00:00Z</responseDate>
          <error code="noRecordsMatch">none</error></OAI-PMH>"""
        page = parse_page(source)
        self.assertEqual(page.records, ())
        self.assertIsNone(page.token)
        self.assertEqual(page.response_date, "2026-01-03T00:00:00Z")


class OaiClientTests(unittest.TestCase):
    class Clock:
        def __init__(self):
            self.value = 0.0
            self.waits = []

        def __call__(self):
            return self.value

        def sleep(self, delay):
            self.waits.append(delay)
            self.value += delay

    class Response(io.BytesIO):
        def __init__(self, body, length=None):
            super().__init__(body)
            self.headers = {}
            if length is not None:
                self.headers["Content-Length"] = str(length)

    def test_urls(self) -> None:
        initial = build_url(date(2005, 9, 16), "2005-12-31")
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(initial).query)
        self.assertEqual(params["verb"], ["ListRecords"])
        self.assertEqual(params["metadataPrefix"], ["arXiv"])
        self.assertEqual(params["from"], ["2005-09-16"])
        self.assertEqual(params["until"], ["2005-12-31"])

        resumed = build_url(start="ignored", token="a token")
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(resumed).query)
        self.assertEqual(
            params, {"verb": ["ListRecords"], "resumptionToken": ["a token"]}
        )

        timed = build_url(datetime(2020, 2, 3, 23, 59), date(2020, 2, 4))
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(timed).query)
        self.assertEqual(params["from"], ["2020-02-03"])
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            build_url(start="2020-02-03T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "must not follow"):
            build_url(start="2020-02-04", end="2020-02-03")

        request = post_request(initial)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://oaipmh.arxiv.org/oai")
        self.assertEqual(
            urllib.parse.parse_qs(request.data.decode()),
            params | {"from": ["2005-09-16"], "until": ["2005-12-31"]},
        )

    def test_resume(self) -> None:
        requests = []
        payloads = iter((PAGE, DONE))

        def opener(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 10)
            return self.Response(next(payloads))

        clock = self.Clock()
        client = OaiClient(
            timeout=10,
            delay=0.25,
            opener=opener,
            sleeper=clock.sleep,
            clock=clock,
        )
        records = list(client.records(start="2024-01-01"))

        self.assertEqual(len(records), 3)
        self.assertTrue(all(request.get_method() == "POST" for request in requests))
        first = urllib.parse.parse_qs(requests[0].data.decode())
        second = urllib.parse.parse_qs(requests[1].data.decode())
        self.assertEqual(first["metadataPrefix"], ["arXiv"])
        self.assertEqual(second["resumptionToken"], ["next \n token"])
        self.assertEqual(clock.waits, [0.25])

    def test_identify(self) -> None:
        urls = []

        def opener(request, timeout):
            urls.append(request.full_url)
            return self.Response(IDENTIFY)

        client = OaiClient(delay=0, opener=opener, sleeper=lambda _: None)
        first = client.identify()
        second = client.identify()

        self.assertIs(first, second)
        self.assertEqual(len(urls), 1)
        self.assertIn("verb=Identify", urls[0])

    def test_preflight(self) -> None:
        urls = []
        payloads = iter((IDENTIFY, DONE))

        def opener(request, timeout):
            urls.append(request.full_url)
            return self.Response(next(payloads))

        client = OaiClient(
            delay=0,
            opener=opener,
            sleeper=lambda _: None,
            official=True,
        )
        pages = list(client.pages())

        self.assertEqual(len(pages), 1)
        self.assertIn("verb=Identify", urls[0])
        self.assertEqual(urls[1], "https://oaipmh.arxiv.org/oai")

    def test_fetch_cadence(self) -> None:
        clock = self.Clock()
        starts = []

        def opener(request, timeout):
            starts.append(clock())
            return self.Response(DONE)

        client = OaiClient(
            delay=0.5,
            opener=opener,
            sleeper=clock.sleep,
            clock=clock,
        )
        client.fetch()
        clock.value += 0.1
        client.fetch()

        self.assertEqual(starts, [0.0, 0.5])
        self.assertAlmostEqual(clock.waits[0], 0.4)

    def test_retry(self) -> None:
        attempts = 0
        clock = self.Clock()

        def opener(request, timeout):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise HTTPError(
                    request.full_url, 503, "busy", {"Retry-After": "2"}, None
                )
            if attempts == 2:
                raise URLError("temporary")
            return self.Response(DONE)

        client = OaiClient(
            retries=2,
            delay=0.5,
            opener=opener,
            sleeper=clock.sleep,
            clock=clock,
        )
        page = client.fetch()

        self.assertEqual(len(page.records), 1)
        self.assertEqual(attempts, 3)
        self.assertEqual(clock.waits, [2.0, 1.0])

    def test_permanent(self) -> None:
        def opener(request, timeout):
            raise HTTPError(request.full_url, 400, "bad", {}, None)

        client = OaiClient(retries=3, delay=0, opener=opener, sleeper=lambda _: None)
        with self.assertRaises(HTTPError):
            client.fetch()

    def test_bad_delay(self) -> None:
        attempts = 0
        clock = self.Clock()

        def opener(request, timeout):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise HTTPError(
                    request.full_url, 429, "slow", {"Retry-After": "invalid"}, None
                )
            return self.Response(DONE)

        client = OaiClient(
            retries=1,
            delay=0.5,
            opener=opener,
            sleeper=clock.sleep,
            clock=clock,
        )
        client.fetch()
        self.assertEqual(clock.waits, [0.5])

    def test_page_limit(self) -> None:
        def opener(request, timeout):
            return self.Response(b"", PAGE_LIMIT + 1)

        client = OaiClient(opener=opener, sleeper=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "exceeds"):
            client.fetch()

    def test_cadence(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 3 seconds"):
            OaiClient(delay=2.9)
        OaiClient(delay=0, sleeper=lambda _: None)

    def test_expiry(self) -> None:
        page = parse_page(PAGE)
        before = datetime(2099, 1, 1, tzinfo=timezone.utc)
        expires = datetime(2099, 1, 2, tzinfo=timezone.utc)
        self.assertFalse(token_expired(page, before))
        self.assertTrue(token_expired(page, expires))

        expired = PAGE.replace(b"2099-01-02", b"2020-01-02")
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            return self.Response(expired)

        client = OaiClient(
            delay=0,
            opener=opener,
            sleeper=lambda _: None,
            now=lambda: datetime(2021, 1, 1, tzinfo=timezone.utc),
        )
        pages = client.pages()
        with self.assertRaisesRegex(OaiError, "response token expired"):
            next(pages)
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
