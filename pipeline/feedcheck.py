"""Validate daily intake completeness, ranking, archives, and public copies."""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from ontology import TOPICS, TRICKS
from rules import check
from titles import valid_title

ROOT = Path(__file__).resolve().parents[1]
FEED_ROOT = ROOT / "data/generated/feed"
PUBLIC_ROOT = ROOT / "web/public/data/feed"
DAY_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def load_json(path: Path) -> dict:
    """Load one generated object with a path-specific contract error."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid daily feed artifact: {path}") from error
    check(isinstance(value, dict), f"Daily feed artifact is not an object: {path}")
    return value


def valid_score(value: object) -> bool:
    """Accept finite one-decimal triage scores on the documented scale."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 10
        and round(float(value), 1) == value
    )


def validate_paper(paper: dict, day: str) -> None:
    """Validate one relevance-positive, auditable public paper row."""
    identifier = paper.get("id")
    check(bool(identifier), f"Daily paper without ID on {day}")
    check(
        paper.get("url") == f"https://arxiv.org/abs/{identifier}",
        f"Unsafe daily arXiv URL on {identifier}",
    )
    check(
        all(isinstance(paper.get(key), str) for key in ("title", "abstract")),
        f"Invalid daily text on {identifier}",
    )
    check(valid_title(paper.get("title")), f"Unsafe daily title on {identifier}")
    check(
        isinstance(paper.get("authors"), list)
        and isinstance(paper.get("categories"), list),
        f"Invalid daily bibliography on {identifier}",
    )
    relevance = paper.get("relevance", {})
    interest = paper.get("interest", {})
    check(relevance.get("relevant") is True, f"Rejected paper published on {day}")
    check(
        relevance.get("lane") in {"core", "field", "math-stat", "adjacent"},
        f"Invalid relevance lane on {identifier}",
    )
    check(
        valid_score(relevance.get("score")) and valid_score(interest.get("score")),
        f"Invalid daily score on {identifier}",
    )
    check(
        {route.get("id") for route in paper.get("topics", [])} <= set(TOPICS),
        f"Unknown daily topic on {identifier}",
    )
    check(
        {route.get("id") for route in paper.get("tricks", [])} <= set(TRICKS),
        f"Unknown daily technique on {identifier}",
    )


def validate_raw(path: Path, payload: dict) -> None:
    """Require the private archive to prove the public day's source counts."""
    check(path.exists(), f"Missing raw daily intake: {path}")
    try:
        raw = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, gzip.BadGzipFile, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid raw daily intake: {path}") from error
    source = payload["source"]
    check(raw.get("date") == payload["date"], f"Raw daily date mismatch: {path}")
    check(
        raw.get("source_total") == source["source_total"]
        and raw.get("fetched_count") == source["fetched_count"],
        f"Raw daily counts mismatch: {path}",
    )
    check(
        len(raw.get("papers", [])) == source["source_total"],
        f"Raw daily archive is incomplete: {path}",
    )
    raw_ids = [paper.get("id") for paper in raw["papers"]]
    check(
        len(set(raw_ids)) == source["unique_count"],
        f"Raw daily unique count mismatch: {path}",
    )


def validate_day(path: Path) -> dict:
    """Validate completeness, counts, ordering, and raw lineage for one day."""
    payload = load_json(path)
    day = path.stem
    check(payload.get("date") == day, f"Daily filename/date mismatch: {path}")
    source = payload.get("source", {})
    check(source.get("complete") is True, f"Incomplete daily intake: {day}")
    check(
        source.get("source_total") == source.get("fetched_count"),
        f"Daily source/fetch count mismatch: {day}",
    )
    papers = payload.get("papers", [])
    check(
        isinstance(papers, list) and len(papers) == payload.get("relevant_count"),
        f"Daily relevant count mismatch: {day}",
    )
    ids = [paper.get("id") for paper in papers]
    check(len(ids) == len(set(ids)), f"Duplicate daily paper IDs: {day}")
    shortlist = payload.get("shortlist_ids", [])
    check(
        isinstance(shortlist, list)
        and len(shortlist) == payload.get("shortlist_count")
        and shortlist == ids[: len(shortlist)],
        f"Invalid daily shortlist: {day}",
    )
    for paper in papers:
        validate_paper(paper, day)
    scores = [
        (
            -paper["interest"]["score"],
            -paper["relevance"]["score"],
            paper["title"].casefold(),
            paper["id"],
        )
        for paper in papers
    ]
    check(scores == sorted(scores), f"Daily papers are not ranked: {day}")
    validate_raw(FEED_ROOT / "raw" / f"{path.name}.gz", payload)
    return payload


def validate_copy(path: Path, roots: list[Path]) -> None:
    """Require every served feed artifact to match its generated source."""
    for root in roots:
        copy = root / path.name
        check(copy.exists(), f"Missing published daily artifact: {copy}")
        check(copy.read_bytes() == path.read_bytes(), f"Stale daily artifact: {copy}")


def validate_feed(include_dist: bool = True) -> None:
    """Validate the indexed daily feed as one complete publication unit."""
    index_path = FEED_ROOT / "index.json"
    check(index_path.exists(), "Daily feed index is missing")
    index = load_json(index_path)
    day_paths = sorted(
        (path for path in FEED_ROOT.glob("*.json") if DAY_NAME.fullmatch(path.name)),
        reverse=True,
    )
    indexed = index.get("days", [])
    check(
        [item.get("date") for item in indexed] == [path.stem for path in day_paths],
        "Daily feed index is stale or unsorted",
    )
    public_roots = [PUBLIC_ROOT]
    if include_dist:
        public_roots.append(ROOT / "web/dist/data/feed")
    validate_copy(index_path, public_roots)
    for path, summary in zip(day_paths, indexed, strict=True):
        payload = validate_day(path)
        expected = {
            "source_total": payload["source"]["source_total"],
            "fetched_count": payload["source"]["fetched_count"],
            "relevant_count": payload["relevant_count"],
            "shortlist_count": payload["shortlist_count"],
            "complete": True,
        }
        check(
            all(summary.get(key) == value for key, value in expected.items()),
            f"Daily index summary is stale: {path.stem}",
        )
        validate_copy(path, public_roots)
