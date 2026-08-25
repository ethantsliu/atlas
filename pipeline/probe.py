#!/usr/bin/env python3
"""Verify the anonymous integrity of a deployed static atlas."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable

HTML_LIMIT = 2_000_000
CORE_LIMIT = 2_000_000
PAPER_LIMIT = 8_000_000
DETAIL_LIMIT = 8_000_000
FEED_LIMIT = 20_000_000
SCRIPT_LIMIT = 5_000_000
USER_AGENT = "atlas-probe/1.0"


class ProbeError(RuntimeError):
    """Raised when the live static release fails an integrity check."""


@dataclass(frozen=True)
class Fetched:
    """One bounded anonymous HTTP response."""

    url: str
    status: int
    content_type: str
    body: bytes


Fetcher = Callable[[str, int], Fetched]


class AppParser(HTMLParser):
    """Collect the application root and module scripts from the shell."""

    def __init__(self) -> None:
        super().__init__()
        self.has_root = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "div" and values.get("id") == "root":
            self.has_root = True
        if tag == "script" and values.get("type") == "module" and values.get("src"):
            self.scripts.append(str(values["src"]))


def parse_base(value: str) -> str:
    """Normalize one HTTPS deployment root or a local HTTP test root."""
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as error:
        raise ProbeError("Site URL is invalid") from error
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))
    ):
        raise ProbeError("Site URL must be an HTTPS origin path")
    path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def scoped_url(base: str, target: str, *, data: bool = False) -> str:
    """Resolve a same-deployment URL and reject path or origin escapes."""
    if not isinstance(target, str) or not target:
        raise ProbeError("Asset URL is missing")
    base_parts = urllib.parse.urlsplit(base)
    if data:
        resolved = urllib.parse.urljoin(base, target.lstrip("/"))
    else:
        resolved = urllib.parse.urljoin(base, target)
    parts = urllib.parse.urlsplit(resolved)
    if (
        parts.scheme != base_parts.scheme
        or parts.netloc != base_parts.netloc
        or parts.query
        or parts.fragment
        or not parts.path.startswith(base_parts.path)
    ):
        raise ProbeError(f"Asset URL escapes the deployment root: {target}")
    return resolved


def fetch_url(url: str, limit: int) -> Fetched:
    """Fetch one anonymous response with a strict byte limit."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(limit + 1)
            result = Fetched(
                url=response.geturl(),
                status=response.status,
                content_type=response.headers.get_content_type(),
                body=body,
            )
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ProbeError(f"Request failed for {url}: {error}") from error
    if len(result.body) > limit:
        raise ProbeError(f"Response exceeds {limit} bytes: {url}")
    return result


def get_asset(base: str, url: str, limit: int, fetcher: Fetcher) -> Fetched:
    """Require a successful response that remains inside the deployment."""
    result = fetcher(url, limit)
    final = scoped_url(base, result.url)
    if final != result.url or not 200 <= result.status < 300:
        raise ProbeError(f"Asset request failed ({result.status}): {url}")
    return result


def json_body(result: Fetched, label: str) -> object:
    """Decode one UTF-8 JSON response with a useful failure label."""
    try:
        return json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeError(f"{label} is not valid UTF-8 JSON") from error


def check_html(base: str, fetcher: Fetcher) -> str:
    """Verify the HTML shell and one referenced application module."""
    shell = get_asset(base, base, HTML_LIMIT, fetcher)
    if shell.content_type != "text/html":
        raise ProbeError("Site root is not served as HTML")
    try:
        text = shell.body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProbeError("Site HTML is not valid UTF-8") from error
    parser = AppParser()
    parser.feed(text)
    if not parser.has_root or not parser.scripts:
        raise ProbeError("Site HTML lacks the app root or module script")
    script_url = scoped_url(base, parser.scripts[0])
    script = get_asset(base, script_url, SCRIPT_LIMIT, fetcher)
    if not script.body:
        raise ProbeError("Application module is empty")
    return script_url


def check_core(base: str, fetcher: Fetcher) -> tuple[dict, dict]:
    """Verify the mutable core and its exact immutable paper shard."""
    core_url = scoped_url(base, "/data/atlas.json", data=True)
    core = json_body(get_asset(base, core_url, CORE_LIMIT, fetcher), "Atlas core")
    if not isinstance(core, dict) or core.get("schema_version") != 2:
        raise ProbeError("Atlas core has an unsupported shape")
    asset = core.get("paper_asset")
    if not isinstance(asset, dict):
        raise ProbeError("Atlas core lacks paper asset metadata")
    path = asset.get("path")
    expected_bytes = asset.get("bytes")
    expected_sha = asset.get("sha256")
    if (
        not isinstance(path, str)
        or not isinstance(expected_bytes, int)
        or expected_bytes < 1
        or not isinstance(expected_sha, str)
        or len(expected_sha) != 64
    ):
        raise ProbeError("Paper asset metadata is invalid")
    paper_url = scoped_url(base, path, data=True)
    paper = get_asset(base, paper_url, PAPER_LIMIT, fetcher)
    if len(paper.body) != expected_bytes:
        raise ProbeError("Paper asset byte length does not match the core")
    if hashlib.sha256(paper.body).hexdigest() != expected_sha:
        raise ProbeError("Paper asset digest does not match the core")
    bundle = json_body(paper, "Paper asset")
    if not isinstance(bundle, dict) or not isinstance(bundle.get("papers"), list):
        raise ProbeError("Paper asset has an unsupported shape")
    return core, bundle


def check_reading(base: str, bundle: dict, fetcher: Fetcher) -> str | None:
    """Verify one content-addressed reading when the corpus exposes one."""
    for paper in bundle["papers"]:
        if not isinstance(paper, dict) or not isinstance(
            paper.get("full_reading_path"), str
        ):
            continue
        path = paper["full_reading_path"]
        reading_url = scoped_url(base, path, data=True)
        reading = json_body(
            get_asset(base, reading_url, DETAIL_LIMIT, fetcher), "Reading asset"
        )
        if not isinstance(reading, dict) or reading.get("stable_id") != paper.get(
            "stable_id"
        ):
            raise ProbeError("Reading asset identity does not match its paper")
        return reading_url
    return None


def check_feed(base: str, fetcher: Fetcher) -> str | None:
    """Verify the feed index and one dated asset when a day is present."""
    index_url = scoped_url(base, "/data/feed/index.json", data=True)
    index = json_body(get_asset(base, index_url, FEED_LIMIT, fetcher), "Feed index")
    if not isinstance(index, dict) or not isinstance(index.get("days"), list):
        raise ProbeError("Feed index has an unsupported shape")
    if not index["days"]:
        return None
    summary = index["days"][0]
    if not isinstance(summary, dict) or not isinstance(summary.get("path"), str):
        raise ProbeError("Feed index day is invalid")
    day_url = scoped_url(base, summary["path"], data=True)
    day = json_body(get_asset(base, day_url, FEED_LIMIT, fetcher), "Feed day")
    if not isinstance(day, dict) or day.get("date") != summary.get("date"):
        raise ProbeError("Feed day identity does not match its index")
    return day_url


def run_probe(base: str, fetcher: Fetcher = fetch_url) -> dict:
    """Run every anonymous live-release check and return a compact report."""
    root = parse_base(base)
    script = check_html(root, fetcher)
    core, bundle = check_core(root, fetcher)
    reading = check_reading(root, bundle, fetcher)
    feed = check_feed(root, fetcher)
    return {
        "site": root,
        "script": script,
        "paper_asset": core["paper_asset"]["path"],
        "paper_count": len(bundle["papers"]),
        "reading": reading,
        "feed": feed,
    }


def probe_many(
    base: str,
    attempts: int,
    delay: float,
    fetcher: Fetcher = fetch_url,
) -> dict:
    """Retry a live check briefly to tolerate deployment propagation."""
    if not 1 <= attempts <= 10 or not 0 <= delay <= 30:
        raise ProbeError("Probe retry settings are outside safe bounds")
    last: ProbeError | None = None
    for attempt in range(attempts):
        try:
            return run_probe(base, fetcher)
        except ProbeError as error:
            last = error
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise last or ProbeError("Live atlas probe did not run")


def main() -> None:
    """Parse CLI arguments, run the probe, and print JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    try:
        report = probe_many(args.base_url, args.attempts, args.delay)
    except ProbeError as error:
        raise SystemExit(f"Live atlas probe failed: {error}") from error
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
