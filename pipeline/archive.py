#!/usr/bin/env python3
"""Build deterministic monthly shards for exhaustive arXiv metadata."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from arxivid import valid_id
from files import atomic_write_bytes, atomic_write_text
from ontology import TOPICS, TRICKS
from rank import rank_paper
from scrub import scrub_paper
from titles import valid_title


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "data/cache/archive"
MANIFEST_NAME = "index.json"
SCOPES = ("likely", "possible", "outside")
SHARD_NAME = re.compile(r"^(?P<month>[0-9]{4}-[0-9]{2})(?:-[0-9a-f]{16})?\.json\.gz$")
PRIVATE_ID = re.compile(
    r"(?i)^(?:private|personal|local|repo|repository|device|machine|workspace)[./_-]"
)
UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
MAX_TITLE = 4_096
MAX_ABSTRACT = 1_000_000
MAX_AUTHOR = 4_096
MAX_AUTHORS = 10_000
MAX_META = 512
RELEVANCE_KEYS = frozenset(
    {"relevant", "score", "lane", "reasons", "strong_hits", "support_hits"}
)
INTEREST_KEYS = frozenset({"score", "reasons"})
ROUTE_KEYS = frozenset({"id", "score", "evidence"})
META_BLOCK = re.compile(
    r"(?i)(?:private[_ -]?context|https?://|file://|www\.|"
    r"@[a-z0-9_.-]+|(?:^|[\s\"'(])(?:/(?:users|home|tmp|private)/|"
    r"~[/\\]|[a-z]:[/\\])|(?:localhost|127\.0\.0\.1))"
)
PUBLIC_FIELDS = (
    "id",
    "url",
    "title",
    "abstract",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "scope",
    "relevance",
    "interest",
    "topics",
    "tricks",
)
PUBLIC_KEYS = frozenset(PUBLIC_FIELDS)
LEGACY_KEYS = PUBLIC_KEYS | {"comment"}


def month_key(value: str) -> str:
    """Return the validated UTC month for an arXiv publication timestamp."""
    try:
        parsed = date.fromisoformat(value[:10])
    except (TypeError, ValueError) as error:
        raise ValueError("Archive paper has an invalid publication date") from error
    return parsed.strftime("%Y-%m")


def scope_paper(paper: dict, rules: dict) -> dict:
    """Classify visibility without ever deleting metadata from the archive."""
    ranked = rank_paper(paper, rules)
    relevance = ranked["relevance"]
    if relevance["relevant"]:
        scope = "likely"
    elif relevance["lane"] == "math-stat" or relevance["support_hits"]:
        scope = "possible"
    else:
        scope = "outside"
    return {**ranked, "scope": scope}


def compact_paper(paper: dict) -> dict:
    """Retain searchable metadata while omitting duplicated ranking internals."""
    try:
        result = {key: paper[key] for key in PUBLIC_FIELDS}
    except (KeyError, TypeError) as error:
        raise ValueError("Archive paper fields are incomplete") from error
    result = scrub_paper(result)
    check_paper(result)
    return result


def check_paper(paper: dict) -> None:
    """Enforce a completeness-safe public scholarly-text boundary."""
    identifier = paper.get("id")
    title = paper.get("title")
    abstract = paper.get("abstract")
    authors = paper.get("authors")
    if (
        set(paper) != PUBLIC_KEYS
        or not valid_id(identifier)
        or PRIVATE_ID.search(identifier) is not None
        or not title
        or not safe_text(title, MAX_TITLE)
        or not valid_title(title)
        or not safe_text(abstract, MAX_ABSTRACT)
        or (
            not isinstance(authors, list)
            or len(authors) > MAX_AUTHORS
            or not all(isinstance(author, str) for author in authors)
            or not all(safe_text(author, MAX_AUTHOR) for author in authors)
        )
        or paper.get("url") != f"https://arxiv.org/abs/{identifier}"
        or not text_list(paper.get("categories"))
        or not safe_text(paper.get("primary_category"), MAX_TITLE)
        or not valid_stamp(paper.get("published"))
        or not valid_stamp(paper.get("updated"))
        or paper.get("scope") not in SCOPES
        or not valid_relevance(paper.get("relevance"))
        or not valid_interest(paper.get("interest"))
        or not valid_routes(paper.get("topics"), TOPICS)
        or not valid_routes(paper.get("tricks"), TRICKS)
    ):
        raise ValueError("Archive public paper text is invalid")


def valid_score(value: object) -> bool:
    """Require one finite, single-decimal score on the public scale."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 10
        and round(float(value), 1) == value
    )


def meta_text(value: object) -> bool:
    """Reject private locators from compact derived metadata."""
    return (
        isinstance(value, str)
        and bool(value)
        and safe_text(value, MAX_META)
        and META_BLOCK.search(value) is None
    )


def meta_list(value: object, limit: int) -> bool:
    """Require a short, unique list of safe derived strings."""
    return (
        isinstance(value, list)
        and len(value) <= limit
        and all(isinstance(item, str) for item in value)
        and len(value) == len(set(value))
        and all(meta_text(item) for item in value)
    )


def valid_relevance(value: object) -> bool:
    """Validate the exact public relevance explanation contract."""
    if value == {}:
        return True
    if not isinstance(value, dict) or set(value) != RELEVANCE_KEYS:
        return False
    lane = value.get("lane")
    reasons = value.get("reasons")
    if (
        not isinstance(value.get("relevant"), bool)
        or not valid_score(value.get("score"))
        or lane not in {"core", "field", "math-stat", "adjacent"}
        or not meta_list(reasons, 3)
        or not meta_list(value.get("strong_hits"), 256)
        or not meta_list(value.get("support_hits"), 256)
    ):
        return False
    allowed = (
        "core ML category",
        "ML-intensive field category",
        "strong signals: ",
        "supporting signals: ",
    )
    if not all(
        reason in allowed[:2] or reason.startswith(allowed[2:]) for reason in reasons
    ):
        return False
    lane_reason = {
        "core": "core ML category",
        "field": "ML-intensive field category",
    }.get(lane)
    category_reasons = set(reasons) & set(allowed[:2])
    return category_reasons == ({lane_reason} if lane_reason else set())


def valid_interest(value: object) -> bool:
    """Validate the exact public interest explanation contract."""
    if value == {}:
        return True
    if not isinstance(value, dict) or set(value) != INTEREST_KEYS:
        return False
    reasons = value.get("reasons")
    prefixes = (
        "interest signals: ",
        "priority topics: ",
        "priority methods: ",
    )
    return (
        valid_score(value.get("score"))
        and meta_list(reasons, 3)
        and all(reason.startswith(prefixes) for reason in reasons)
    )


def valid_routes(value: object, ontology: dict[str, list[str]]) -> bool:
    """Validate exact, ontology-backed topic or technique routes."""
    if not isinstance(value, list) or len(value) > 6:
        return False
    identifiers = []
    for route in value:
        if not isinstance(route, dict) or set(route) != ROUTE_KEYS:
            return False
        identifier = route.get("id")
        score = route.get("score")
        evidence = route.get("evidence")
        phrases = ontology.get(identifier) if isinstance(identifier, str) else None
        if (
            phrases is None
            or not isinstance(score, int)
            or isinstance(score, bool)
            or not 1 <= score <= len(phrases)
            or not meta_list(evidence, 4)
            or evidence != sorted(evidence)
            or not set(evidence) <= set(phrases) | {identifier}
            or score < len(evidence)
            or score <= 4
            and score != len(evidence)
            or score > 4
            and len(evidence) != 4
        ):
            return False
        identifiers.append(identifier)
    return len(identifiers) == len(set(identifiers))


def text_list(value: object) -> bool:
    """Require a bounded list of normalized public strings."""
    return (
        isinstance(value, list)
        and len(value) <= MAX_AUTHORS
        and all(safe_text(item, MAX_AUTHOR) for item in value)
    )


def valid_stamp(value: object) -> bool:
    """Accept a normalized ISO day or timezone-aware timestamp."""
    if not isinstance(value, str) or not value:
        return False
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat() == value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def safe_text(value: object, limit: int) -> bool:
    """Accept bounded normalized text from the official scholarly source."""
    if (
        not isinstance(value, str)
        or len(value) > limit
        or value != " ".join(value.split())
    ):
        return False
    return not any(
        unicodedata.category(character) in UNSAFE_CATEGORIES for character in value
    )


def clean_text(value: object) -> str:
    """Normalize controls in one field from the known prior archive schema."""
    if not isinstance(value, str):
        raise ValueError("Archive legacy paper text is invalid")
    visible = "".join(
        " " if unicodedata.category(character) in UNSAFE_CATEGORIES else character
        for character in value
    )
    return " ".join(visible.split())


def clean_legacy(paper: dict) -> dict:
    """Project and sanitize only the one explicitly supported prior schema."""
    result = {key: paper[key] for key in PUBLIC_FIELDS}
    for field in ("title", "abstract", "primary_category"):
        result[field] = clean_text(result[field])
    for field in ("authors", "categories"):
        values = result[field]
        if not isinstance(values, list):
            raise ValueError("Archive legacy paper text is invalid")
        result[field] = [clean_text(value) for value in values]
    return compact_paper(result)


def public_paper(paper: object) -> dict:
    """Remove non-public source fields at the shard persistence boundary."""
    if not isinstance(paper, dict):
        raise ValueError("Archive shard paper is invalid")
    return compact_paper(paper)


def scope_counts(papers: list[dict]) -> dict[str, int]:
    """Count every visibility lane with stable zero-valued keys."""
    return {scope: sum(paper["scope"] == scope for paper in papers) for scope in SCOPES}


def day_row(day: date, intake: dict) -> dict:
    """Record the source completeness proof for one harvested day."""
    return {
        "date": day.isoformat(),
        "source_total": intake["source_total"],
        "fetched_count": intake["fetched_count"],
        "unique_count": intake["unique_count"],
        "page_count": intake["page_count"],
        "query": intake["query"],
        "complete": intake["source_total"] == intake["fetched_count"],
    }


def build_month(day: date, intake: dict, rules: dict) -> dict:
    """Build one exhaustive monthly shard from a complete source day."""
    proof = day_row(day, intake)
    if not proof["complete"] or proof["unique_count"] != proof["source_total"]:
        raise ValueError("Archive ingestion requires one complete, unique source day")
    papers = [compact_paper(scope_paper(paper, rules)) for paper in intake["papers"]]
    if any(month_key(paper["published"]) != day.strftime("%Y-%m") for paper in papers):
        raise ValueError("Archive day contains a paper from another publication month")
    papers.sort(key=lambda paper: paper["id"])
    return {
        "schema_version": 1,
        "policy_version": rules["version"],
        "month": day.strftime("%Y-%m"),
        "days": [proof],
        "counts": {"all": len(papers), **scope_counts(papers)},
        "papers": papers,
    }


def merge_month(prior: dict, current: dict) -> dict:
    """Merge resumable days while preferring the newest paper metadata."""
    if prior.get("month") != current.get("month"):
        raise ValueError("Archive shards belong to different months")
    if prior.get("policy_version") != current.get("policy_version"):
        raise ValueError("Archive shards use different relevance policies")
    days = {row["date"]: row for row in prior["days"]}
    days.update({row["date"]: row for row in current["days"]})
    papers = {paper["id"]: compact_paper(paper) for paper in prior["papers"]}
    for paper in current["papers"]:
        paper = compact_paper(paper)
        saved = papers.get(paper["id"])
        if saved is None or paper["updated"] >= saved["updated"]:
            papers[paper["id"]] = paper
    ordered = sorted(papers.values(), key=lambda paper: paper["id"])
    return {
        "schema_version": 1,
        "policy_version": current["policy_version"],
        "month": current["month"],
        "days": [days[key] for key in sorted(days)],
        "counts": {"all": len(ordered), **scope_counts(ordered)},
        "papers": ordered,
    }


def shard_bytes(payload: dict) -> bytes:
    """Serialize a monthly shard as reproducible compressed JSON."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return gzip.compress(body, compresslevel=9, mtime=0)


def raw_shard(path: Path) -> dict:
    """Decode one bounded shard and verify its root envelope."""
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, EOFError, json.JSONDecodeError) as error:
        raise ValueError(f"Archive shard is invalid: {path.name}") from error
    match = SHARD_NAME.fullmatch(path.name)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or match is None
        or payload.get("month") != match.group("month")
        or not isinstance(payload.get("papers"), list)
        or not isinstance(payload.get("days"), list)
    ):
        raise ValueError(f"Archive shard contract is invalid: {path.name}")
    return payload


def check_rows(payload: dict, path: Path) -> None:
    """Validate exact public rows, ordering, month routing, and counts."""
    papers = payload["papers"]
    if any(not isinstance(paper, dict) for paper in papers):
        raise ValueError(f"Archive shard papers are invalid: {path.name}")
    for paper in papers:
        check_paper(paper)
        if month_key(paper["published"]) != payload["month"]:
            raise ValueError(f"Archive shard papers are invalid: {path.name}")
    identifiers = [paper["id"] for paper in papers]
    if identifiers != sorted(set(identifiers)):
        raise ValueError(f"Archive paper IDs are duplicated or unsorted: {path.name}")
    expected = {"all": len(papers), **scope_counts(papers)}
    if payload.get("counts") != expected:
        raise ValueError(f"Archive shard counts are invalid: {path.name}")


def read_shard(path: Path) -> dict:
    """Read one bounded local archive shard and verify its public contract."""
    payload = raw_shard(path)
    check_rows(payload, path)
    return payload


def migrate_shard(path: Path) -> bool:
    """Rewrite the one known prior schema without losing public metadata."""
    payload = raw_shard(path)
    papers = payload["papers"]
    if not all(
        isinstance(paper, dict) and set(paper) in {PUBLIC_KEYS, LEGACY_KEYS}
        for paper in papers
    ):
        raise ValueError(f"Archive shard papers are invalid: {path.name}")
    cleaned = [clean_legacy(paper) for paper in papers]
    if cleaned == papers:
        check_rows(payload, path)
        return False
    payload = {**payload, "papers": cleaned}
    check_rows(payload, path)
    write_shard(path.parent, payload)
    return True


def migrate_archive(root: Path) -> list[str]:
    """Migrate every local mutable month from the known prior schema."""
    return [
        path.name[:7]
        for path in sorted(root.glob("????-??.json.gz"))
        if migrate_shard(path)
    ]


def write_shard(root: Path, payload: dict) -> Path:
    """Atomically publish one local month shard."""
    month = payload["month"]
    if month_key(f"{month}-01") != month:
        raise ValueError("Archive shard month is invalid")
    papers = payload.get("papers")
    if not isinstance(papers, list):
        raise ValueError("Archive shard papers are invalid")
    payload = {**payload, "papers": [public_paper(paper) for paper in papers]}
    path = root / f"{month}.json.gz"
    atomic_write_bytes(path, shard_bytes(payload))
    return path


def shard_meta(path: Path, seen: set[str] | None = None) -> dict:
    """Describe one content-verified month for the remote object manifest."""
    content = path.read_bytes()
    payload = read_shard(path)
    identifiers = [paper.get("id") for paper in payload["papers"]]
    if (
        not all(
            isinstance(identifier, str) and identifier for identifier in identifiers
        )
        or len(identifiers) != len(set(identifiers))
        or seen is not None
        and not set(identifiers).isdisjoint(seen)
    ):
        raise ValueError("Archive paper IDs are duplicated or invalid")
    if seen is not None:
        seen.update(identifiers)
    return {
        "month": payload["month"],
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "days": len(payload["days"]),
        "dates": [row["date"] for row in payload["days"]],
        "counts": payload["counts"],
    }


def check_ids(root: Path, shards: list[dict]) -> None:
    """Reject duplicate paper identities across available indexed shards."""
    seen: set[str] = set()
    for row in shards:
        if isinstance(row, dict) and isinstance(row.get("path"), str):
            path = root / row["path"]
            if path.is_file():
                shard_meta(path, seen)


def read_manifest(root: Path) -> dict:
    """Read the prior remote index when a resumable worker has one."""
    path = root / MANIFEST_NAME
    if not path.exists():
        return {"schema_version": 1, "shards": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Archive manifest is invalid") from error
    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("shards"), list
    ):
        raise ValueError("Archive manifest contract is invalid")
    check_ids(root, payload["shards"])
    return payload


def build_manifest(root: Path) -> dict:
    """Merge locally changed months into the prior exhaustive archive index."""
    prior = {
        shard["month"]: shard
        for shard in read_manifest(root)["shards"]
        if isinstance(shard, dict) and isinstance(shard.get("month"), str)
    }
    local = {}
    seen: set[str] = set()
    for path in sorted(root.glob("????-??.json.gz")):
        local[path.name.removesuffix(".json.gz")] = shard_meta(path, seen)
    shards = [
        (local.get(month) or prior[month])
        for month in sorted(prior.keys() | local.keys())
    ]
    counts = {
        key: sum(shard["counts"][key] for shard in shards) for key in ("all", *SCOPES)
    }
    return {
        "schema_version": 1,
        "storage": "github-release",
        "retention": "all metadata; no scope is discarded",
        "counts": counts,
        "shards": shards,
    }


def write_manifest(root: Path) -> dict:
    """Atomically publish the current local archive manifest."""
    manifest = build_manifest(root)
    atomic_write_text(
        root / MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def add_day(root: Path, day: date, intake: dict, rules: dict) -> dict:
    """Add or refresh one complete day inside its resumable month shard."""
    current = build_month(day, intake, rules)
    path = root / f"{current['month']}.json.gz"
    payload = merge_month(read_shard(path), current) if path.exists() else current
    write_shard(root, payload)
    return write_manifest(root)
