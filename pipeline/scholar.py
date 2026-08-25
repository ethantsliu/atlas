"""Recover page-preserving HTML conversions from Google Scholar caches."""

from __future__ import annotations

from http.cookiejar import CookieJar
from html.parser import HTMLParser
import html
import re
from pathlib import Path
from urllib.parse import quote_plus, urlsplit
from urllib.request import HTTPCookieProcessor, Request

from files import atomic_write_bytes, atomic_write_text
from identity import is_cache_url, query_values
from urls import open_safe, read_limited, safe_opener


SCHOLAR_HOST = "scholar.google.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 "
    "atlas/0.1"
)
PAGE_HEADER = re.compile(
    r"<table\s+border=0\s+width=100%>.*?<b>Page\s+(\d+)</b>.*?</table>",
    re.IGNORECASE | re.DOTALL,
)
LATEX_SOURCE = re.compile(
    r"&lt;latexit\b.*?&lt;/latexit&gt;",
    re.IGNORECASE | re.DOTALL,
)
BASE_HREF = re.compile(r"<base\s+href=[\"']([^\"']+)[\"']", re.IGNORECASE)
MAX_SEARCH_BYTES = 4 * 1024 * 1024
MAX_CACHE_BYTES = 64 * 1024 * 1024


class LinkParser(HTMLParser):
    """Collect links without adding an HTML parsing dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        if values.get("href"):
            self.links.append(values["href"] or "")


class TextParser(HTMLParser):
    """Collect visible converter text while ignoring styling metadata."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"style", "script"}:
            self.hidden += 1
        if lowered == "img" and not self.hidden:
            alternate = dict(attrs).get("alt")
            if alternate:
                self.parts.append(alternate)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"style", "script"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def query_url(title: str) -> str:
    """Build the exact-title Scholar query used to discover one cache."""
    quoted = quote_plus(f'"{title}"')
    return f"https://{SCHOLAR_HOST}/scholar?q={quoted}"


def cache_link(search_html: str) -> str:
    """Select the single public Scholar cache link from a result page."""
    parser = LinkParser()
    parser.feed(search_html)
    links = []
    for link in parser.links:
        try:
            links.append(verify_link(html.unescape(link)))
        except ValueError:
            continue
    unique = list(dict.fromkeys(links))
    if len(unique) != 1:
        raise RuntimeError(f"Expected one Scholar cache link, found {len(unique)}")
    return unique[0]


def verify_link(link: str) -> str:
    """Validate the narrowly approved public-cache URL shape."""
    normalized = html.unescape(link)
    if not is_cache_url(normalized):
        raise ValueError("Invalid Scholar cache URL")
    return normalized


def verify_cache(payload: bytes, stable_id: str) -> None:
    """Require the cached document to identify the exact OpenReview forum."""
    if not stable_id.startswith("openreview:"):
        raise RuntimeError("Scholar cache requires an OpenReview stable ID")
    text = payload.decode("utf-8", errors="strict")
    match = BASE_HREF.search(text)
    if not match:
        raise RuntimeError("Scholar cache is missing its source base URL")
    parsed = urlsplit(html.unescape(match.group(1)))
    expected = stable_id.removeprefix("openreview:")
    query = query_values(parsed.query, {"id"})
    if (
        parsed.scheme != "https"
        or parsed.netloc != "openreview.net"
        or parsed.path != "/forum"
        or parsed.fragment
        or query != {"id": expected}
    ):
        raise RuntimeError("Scholar cache does not match the requested OpenReview ID")


def fetch_cache(
    title: str,
    stable_id: str,
    destination: Path,
    source_url: str | None = None,
) -> str:
    """Fetch one cache through the Scholar result session and preserve its bytes."""
    opener = safe_opener(HTTPCookieProcessor(CookieJar()))
    search_url = query_url(title)
    if source_url:
        link = verify_link(source_url)
        referer = f"https://{SCHOLAR_HOST}/"
    else:
        request = Request(search_url, headers={"User-Agent": USER_AGENT})
        with open_safe(opener, request, timeout=120) as response:
            search = read_limited(response, MAX_SEARCH_BYTES)
        link = cache_link(search.decode("utf-8", errors="strict"))
        referer = search_url
    request = Request(
        link,
        headers={"User-Agent": USER_AGENT, "Referer": referer},
    )
    with open_safe(opener, request, timeout=120) as response:
        payload = read_limited(response, MAX_CACHE_BYTES)
    verify_cache(payload, stable_id)
    temporary = destination.with_suffix(".partial")
    atomic_write_bytes(temporary, payload)
    temporary.replace(destination)
    return link


def page_texts(payload: bytes) -> list[str]:
    """Extract one visible-text body for every numbered converted page."""
    raw = payload.decode("utf-8", errors="strict")
    raw = LATEX_SOURCE.sub(" ", raw)
    headers = list(PAGE_HEADER.finditer(raw))
    page_numbers = [int(match.group(1)) for match in headers]
    if not headers or page_numbers != list(range(1, len(headers) + 1)):
        raise RuntimeError("Scholar cache has incomplete or unordered page markers")
    pages = []
    for index, marker in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(raw)
        parser = TextParser()
        parser.feed(raw[marker.end() : end])
        pages.append(" ".join(" ".join(parser.parts).split()))
    if any(len(page) < 40 for page in pages):
        raise RuntimeError("Scholar cache contains an unusable converted page")
    return pages


def cache_text(payload: bytes) -> str:
    """Format one verified conversion with stable atlas page markers."""
    pages = page_texts(payload)
    return (
        "".join(
            f"\n\n<<<PAGE {number}>>>\n\n{body}"
            for number, body in enumerate(pages, start=1)
        ).strip()
        + "\n"
    )


def load_cache(source: Path) -> bytes:
    """Read one cached conversion only after enforcing its byte ceiling."""
    if source.stat().st_size > MAX_CACHE_BYTES:
        raise RuntimeError(f"Scholar cache exceeds {MAX_CACHE_BYTES} bytes")
    return source.read_bytes()


def extract_cache(source: Path, destination: Path) -> int:
    """Write converted pages with the atlas's stable page-marker contract."""
    payload = load_cache(source)
    pages = page_texts(payload)
    text = cache_text(payload)
    atomic_write_text(destination, text)
    return len(pages)
