#!/usr/bin/env python3
"""Build deterministic monthly shards for exhaustive arXiv metadata."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

from files import atomic_write_bytes, atomic_write_text
from rank import rank_paper


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "data/cache/archive"
MANIFEST_NAME = "index.json"
SCOPES = ("likely", "possible", "outside")


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
    return {
        key: paper[key]
        for key in (
            "id",
            "url",
            "title",
            "abstract",
            "authors",
            "categories",
            "primary_category",
            "published",
            "updated",
            "comment",
            "scope",
            "relevance",
            "interest",
            "topics",
            "tricks",
        )
    }


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
    papers = {paper["id"]: paper for paper in prior["papers"]}
    for paper in current["papers"]:
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


def read_shard(path: Path) -> dict:
    """Read one bounded local archive shard and verify its root contract."""
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, EOFError, json.JSONDecodeError) as error:
        raise ValueError(f"Archive shard is invalid: {path.name}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("month") != path.name.removesuffix(".json.gz")
        or not isinstance(payload.get("papers"), list)
        or not isinstance(payload.get("days"), list)
    ):
        raise ValueError(f"Archive shard contract is invalid: {path.name}")
    return payload


def write_shard(root: Path, payload: dict) -> Path:
    """Atomically publish one local month shard."""
    month = payload["month"]
    if month_key(f"{month}-01") != month:
        raise ValueError("Archive shard month is invalid")
    path = root / f"{month}.json.gz"
    atomic_write_bytes(path, shard_bytes(payload))
    return path


def shard_meta(path: Path) -> dict:
    """Describe one content-verified month for the remote object manifest."""
    content = path.read_bytes()
    payload = read_shard(path)
    return {
        "month": payload["month"],
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "days": len(payload["days"]),
        "dates": [row["date"] for row in payload["days"]],
        "counts": payload["counts"],
    }


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
    return payload


def build_manifest(root: Path) -> dict:
    """Merge locally changed months into the prior exhaustive archive index."""
    prior = {
        shard["month"]: shard
        for shard in read_manifest(root)["shards"]
        if isinstance(shard, dict) and isinstance(shard.get("month"), str)
    }
    local = {
        path.name.removesuffix(".json.gz"): shard_meta(path)
        for path in sorted(root.glob("????-??.json.gz"))
    }
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
