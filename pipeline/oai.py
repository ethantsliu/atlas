#!/usr/bin/env python3
"""Read arXiv's official OAI-PMH metadata feed."""

from __future__ import annotations

import email.utils
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Iterator
from urllib.error import HTTPError, URLError

from arxivid import paper_id
from urls import open_public, read_limited

BASE_URL = "https://oaipmh.arxiv.org/oai"
PREFIX = "arXiv"
REPOSITORY = "arXiv"
EARLIEST = "2005-09-16"
GRANULARITY = "YYYY-MM-DD"
DELETIONS = "persistent"
RETRY_CODES = {429, 500, 502, 503, 504}
USER_AGENT = "Atlas/0.2 (+https://xn--rss.to/atlas/)"
PAGE_LIMIT = 32 * 1024 * 1024
MIN_DELAY = 3.0
BIDI = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
RECORD_FIELDS = {
    "id",
    "url",
    "title",
    "abstract",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "datestamp",
    "deleted",
}


class OaiError(RuntimeError):
    """An error returned in a valid OAI-PMH response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Page:
    """One immutable ListRecords response."""

    records: tuple[dict, ...]
    token: str | None
    cursor: int | None = None
    total: int | None = None
    expires: str | None = None
    response_date: str | None = None


@dataclass(frozen=True)
class Identity:
    """Repository policy required for an exhaustive OAI harvest."""

    repository: str
    base: str
    earliest: str
    granularity: str
    deletions: str


def local(node: ET.Element) -> str:
    """Return an XML name without its namespace."""
    return node.tag.rsplit("}", 1)[-1]


def child(node: ET.Element | None, name: str) -> ET.Element | None:
    """Find a direct child by namespace-independent name."""
    if node is None:
        return None
    return next((item for item in node if local(item) == name), None)


def children(node: ET.Element | None, name: str) -> list[ET.Element]:
    """Find direct children by namespace-independent name."""
    if node is None:
        return []
    return [item for item in node if local(item) == name]


def clean(value: str | None) -> str | None:
    """Collapse XML whitespace while preserving missing values."""
    if value is None:
        return None
    result = " ".join(BIDI.sub("", value).split())
    return result or None


def content(node: ET.Element | None, name: str) -> str | None:
    """Read and normalize one direct child value."""
    item = child(node, name)
    return clean(item.text) if item is not None else None


def id_content(node: ET.Element | None, name: str) -> str | None:
    """Read an identifier without sanitizing invalid control characters."""
    item = child(node, name)
    return item.text.strip() if item is not None and item.text else None


def author_name(node: ET.Element) -> str | None:
    """Build a human-readable name from arXiv author fields."""
    parts = [
        content(node, "forenames"),
        content(node, "keyname"),
        content(node, "suffix"),
    ]
    return clean(" ".join(part for part in parts if part))


def raw_authors(value: str | None) -> list[str]:
    """Split the arXivRaw author convention without losing its source text."""
    if not value:
        return []
    return [name for part in value.split(" and ") if (name := clean(part))]


def parse_authors(node: ET.Element | None) -> list[str]:
    """Parse structured arXiv names or the arXivRaw author string."""
    authors = child(node, "authors")
    if authors is None:
        return []
    structured = [
        name for item in children(authors, "author") if (name := author_name(item))
    ]
    return structured or raw_authors(clean(authors.text))


def split_cats(value: str | None) -> list[str]:
    """Split arXiv's space-separated category field."""
    return value.split() if value else []


def raw_date(value: str | None) -> str:
    """Normalize one legacy RFC-style version timestamp to a UTC day."""
    if not value:
        raise ValueError("arXivRaw version is missing its date")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError) as error:
        try:
            parsed = email.utils.parsedate_to_datetime(f"{value} 00:00:00 GMT")
        except (TypeError, ValueError):
            raise ValueError("arXivRaw version has an invalid date") from error
    if parsed is None:
        raise ValueError("arXivRaw version has an invalid date")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.date().isoformat()


def raw_dates(node: ET.Element) -> list[str]:
    """Read private fallback dates without exposing version history."""
    return [raw_date(content(item, "date")) for item in children(node, "version")]


def record_id(value: str | None) -> str:
    """Validate and extract an identifier from an arXiv OAI header."""
    marker = "oai:arXiv.org:"
    if not value or not value.startswith(marker):
        raise ValueError("OAI header has an invalid arXiv identifier")
    return paper_id(value[len(marker) :])


def parse_record(node: ET.Element) -> dict:
    """Parse one normal or deleted OAI-PMH record."""
    header = child(node, "header")
    if header is None:
        raise ValueError("OAI record is missing its header")
    identifier = record_id(id_content(header, "identifier"))
    datestamp = content(header, "datestamp")
    deleted = header.attrib.get("status") == "deleted"
    if deleted:
        return {
            "id": identifier,
            "datestamp": datestamp,
            "deleted": True,
        }
    metadata = child(node, "metadata")
    body = next(iter(metadata), None) if metadata is not None else None
    if body is None:
        raise ValueError("Active OAI record is missing its metadata")
    body_id = id_content(body, "id")
    if body_id is not None and paper_id(body_id) != identifier:
        raise ValueError("OAI header and metadata identifiers do not match")
    dates = raw_dates(body)
    published = content(body, "created") or (dates[0] if dates else None)
    updated = content(body, "updated") or (dates[-1] if dates else published)
    categories = split_cats(content(body, "categories"))
    result = {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}" if identifier else None,
        "title": content(body, "title"),
        "abstract": content(body, "abstract"),
        "authors": parse_authors(body),
        "categories": categories,
        "primary_category": categories[0] if categories else None,
        "published": published,
        "updated": updated,
        "datestamp": content(header, "datestamp"),
        "deleted": False,
    }
    if set(result) != RECORD_FIELDS:
        raise AssertionError("OAI record field contract changed")
    return result


def parse_count(value: str | None, field: str) -> int | None:
    """Parse one optional non-negative OAI count attribute."""
    if value is None:
        return None
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError(f"OAI {field} is invalid") from error
    if result < 0 or str(result) != value:
        raise ValueError(f"OAI {field} is invalid")
    return result


def parse_page(source: bytes | str) -> Page:
    """Parse one complete OAI-PMH ListRecords document."""
    root = ET.fromstring(source)
    response_date = content(root, "responseDate")
    error = next((item for item in root if local(item) == "error"), None)
    if error is not None:
        if error.attrib.get("code") == "noRecordsMatch":
            return Page(records=(), token=None, response_date=response_date)
        raise OaiError(
            error.attrib.get("code", "unknown"),
            clean(error.text) or "OAI request failed",
        )
    listing = next((item for item in root if local(item) == "ListRecords"), None)
    if listing is None:
        raise ValueError("OAI response has no ListRecords element")
    records = tuple(parse_record(item) for item in children(listing, "record"))
    token_node = child(listing, "resumptionToken")
    token = (
        token_node.text.strip() if token_node is not None and token_node.text else None
    )
    token = token or None
    return Page(
        records=records,
        token=token,
        cursor=parse_count(token_node.attrib.get("cursor"), "cursor")
        if token_node is not None
        else None,
        total=parse_count(token_node.attrib.get("completeListSize"), "total")
        if token_node is not None
        else None,
        expires=clean(token_node.attrib.get("expirationDate"))
        if token_node is not None
        else None,
        response_date=response_date,
    )


def parse_identity(source: bytes | str) -> Identity:
    """Parse and enforce the official arXiv repository policy."""
    root = ET.fromstring(source)
    error = next((item for item in root if local(item) == "error"), None)
    if error is not None:
        raise OaiError(
            error.attrib.get("code", "unknown"),
            clean(error.text) or "OAI request failed",
        )
    node = next((item for item in root if local(item) == "Identify"), None)
    if node is None:
        raise ValueError("OAI response has no Identify element")
    identity = Identity(
        repository=content(node, "repositoryName") or "",
        base=content(node, "baseURL") or "",
        earliest=content(node, "earliestDatestamp") or "",
        granularity=content(node, "granularity") or "",
        deletions=content(node, "deletedRecord") or "",
    )
    expected = Identity(REPOSITORY, BASE_URL, EARLIEST, GRANULARITY, DELETIONS)
    if identity != expected:
        raise ValueError("OAI repository policy changed")
    return identity


def date_text(value: date | datetime | str) -> str:
    """Format and validate one day at OAI's supported granularity."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    result = value.isoformat() if isinstance(value, date) else value
    try:
        parsed = date.fromisoformat(result)
    except (TypeError, ValueError) as error:
        raise ValueError("OAI dates must use YYYY-MM-DD") from error
    if parsed.isoformat() != result:
        raise ValueError("OAI dates must use YYYY-MM-DD")
    return result


def build_url(
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    token: str | None = None,
    prefix: str = PREFIX,
    base: str = BASE_URL,
) -> str:
    """Build a valid initial or resumed ListRecords URL."""
    params = {"verb": "ListRecords"}
    if token:
        params["resumptionToken"] = token
    else:
        params["metadataPrefix"] = prefix
        start_text = date_text(start) if start is not None else None
        end_text = date_text(end) if end is not None else None
        if start_text and end_text and start_text > end_text:
            raise ValueError("OAI start date must not follow its end date")
        if start is not None:
            params["from"] = start_text
        if end is not None:
            params["until"] = end_text
    return f"{base}?{urllib.parse.urlencode(params)}"


def retry_wait(
    error: HTTPError,
    fallback: float,
    current: datetime | None = None,
) -> float:
    """Honor Retry-After seconds or dates, falling back to backoff."""
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return fallback
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return fallback
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now = current or datetime.now(timezone.utc)
        return max(0.0, (parsed - now).total_seconds())


def utc_now() -> datetime:
    """Return a timezone-aware wall-clock timestamp."""
    return datetime.now(timezone.utc)


def token_expired(page: Page, current: datetime | None = None) -> bool:
    """Check an advertised resumption-token expiry deterministically."""
    if not page.expires:
        return False
    try:
        expires = datetime.fromisoformat(page.expires.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("OAI token expiry is invalid") from error
    if expires.tzinfo is None:
        raise ValueError("OAI token expiry must include a timezone")
    now = current or utc_now()
    if now.tzinfo is None:
        raise ValueError("current token time must include a timezone")
    return now >= expires


class OaiClient:
    """Small restartable client for arXiv OAI-PMH ListRecords pages."""

    def __init__(
        self,
        base: str = BASE_URL,
        timeout: float = 90,
        retries: int = 4,
        delay: float = 3.1,
        opener: Callable = open_public,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
        official: bool | None = None,
    ) -> None:
        if retries < 0:
            raise ValueError("retries cannot be negative")
        if delay < MIN_DELAY and sleeper is time.sleep:
            raise ValueError("production delay must be at least 3 seconds")
        if official is not None and not isinstance(official, bool):
            raise ValueError("official transport flag must be boolean")
        self.base = base
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock
        self.now = now
        self.last_request: float | None = None
        self.identity: Identity | None = None
        self.official = (
            base == BASE_URL and opener is open_public if official is None else official
        )

    def wait_turn(self, minimum: float = 0) -> None:
        """Enforce cadence immediately before every network request."""
        current = self.clock()
        elapsed = None if self.last_request is None else current - self.last_request
        cadence = 0 if elapsed is None else max(0.0, self.delay - elapsed)
        wait = max(minimum, cadence)
        if wait > 0:
            self.sleeper(wait)
            current = self.clock()
        self.last_request = current

    def request(self, url: str) -> bytes:
        """Read one OAI response with bounded transient retries."""
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        minimum = 0.0
        for attempt in range(self.retries + 1):
            self.wait_turn(minimum)
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    return read_limited(response, PAGE_LIMIT)
            except HTTPError as error:
                if error.code not in RETRY_CODES or attempt == self.retries:
                    raise
                minimum = retry_wait(
                    error,
                    self.delay * (2**attempt),
                    self.now(),
                )
            except (URLError, TimeoutError):
                if attempt == self.retries:
                    raise
                minimum = self.delay * (2**attempt)
        raise AssertionError("retry loop ended without a result")

    def identify(self) -> Identity:
        """Validate official repository guarantees once per client."""
        if self.identity is None:
            url = f"{self.base}?{urllib.parse.urlencode({'verb': 'Identify'})}"
            self.identity = parse_identity(self.request(url))
        return self.identity

    def fetch(
        self,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
        token: str | None = None,
    ) -> Page:
        """Fetch and parse one page with bounded transient retries."""
        url = build_url(start, end, token, base=self.base)
        return parse_page(self.request(url))

    def pages(
        self,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
        token: str | None = None,
    ) -> Iterator[Page]:
        """Yield every response page while following opaque tokens."""
        if self.official:
            self.identify()
        page = self.fetch(start, end, token)
        while True:
            yield page
            if not page.token:
                return
            if token_expired(page, self.now()):
                raise OaiError("badResumptionToken", "resumption token expired")
            page = self.fetch(token=page.token)

    def records(
        self,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
        token: str | None = None,
    ) -> Iterator[dict]:
        """Yield records across all resumed pages."""
        for page in self.pages(start, end, token):
            yield from page.records
