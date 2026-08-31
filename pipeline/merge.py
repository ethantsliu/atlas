#!/usr/bin/env python3
"""Promote sealed OAI pages into deterministic monthly archive shards."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from arxivid import paper_id
from archive import (
    UNSAFE_CATEGORIES,
    compact_paper,
    migrate_archive,
    month_key,
    read_manifest,
    read_shard,
    scope_counts,
    scope_paper,
    write_manifest,
    write_shard,
)
from harvest import read_page, read_state, stage_path
from events import (
    check_ledger,
    event_stamp,
    filter_events,
    finish_merge,
    iso_date,
    ledger_needed,
    merge_path,
    open_ledger,
    save_events,
    start_merge,
)


PAPER_FIELDS = (
    "id",
    "url",
    "title",
    "abstract",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
)


def clean_list(value: object, field: str) -> list[str]:
    """Normalize one public list without accepting nested metadata."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"OAI record has invalid {field}")
    return [cleaned for item in value if (cleaned := clean_value(item))]


def clean_value(value: str) -> str:
    """Remove display controls before normalizing official source text."""
    visible = "".join(
        " " if unicodedata.category(character) in UNSAFE_CATEGORIES else character
        for character in value
    )
    return " ".join(visible.split())


def clean_text(value: object, field: str, *, empty: bool = False) -> str:
    """Normalize one public text field with an explicit empty policy."""
    if value is None and empty:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"OAI record has invalid {field}")
    cleaned = clean_value(value)
    if not cleaned and not empty:
        raise ValueError(f"OAI record has empty {field}")
    return cleaned


def normalize_paper(record: dict) -> dict:
    """Project an active OAI record into the archive's minimal source fields."""
    identifier = clean_text(record.get("id"), "id").lower()
    title = clean_text(record.get("title"), "title", empty=True)
    if not title:
        title = f"arXiv {identifier}"
    categories = clean_list(record.get("categories"), "categories")
    published = iso_date(record.get("published"), "published")
    updated = iso_date(record.get("updated") or published, "updated")
    primary = record.get("primary_category") or (categories[0] if categories else "")
    if not isinstance(primary, str):
        raise ValueError("OAI record has invalid primary_category")
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": title,
        "abstract": clean_text(record.get("abstract"), "abstract", empty=True),
        "authors": clean_list(record.get("authors"), "authors"),
        "categories": categories,
        "primary_category": " ".join(primary.split()),
        "published": published,
        "updated": updated,
    }


def read_generation(root: Path, generation: str) -> dict:
    """Require an atomically sealed harvest generation before promotion."""
    state = read_state(root, generation)
    path = stage_path(root, generation) / "index.json"
    if state is None or state.get("status") != "complete" or not path.is_file():
        raise ValueError("OAI generation is not sealed")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("OAI generation index is unreadable") from error
    expected = {key: value for key, value in state.items() if key != "next_token"}
    expected["sealed"] = True
    if manifest != expected:
        raise ValueError("OAI generation index drifted from its checkpoint")
    return manifest


def page_records(root: Path, generation: str, manifest: dict):
    """Yield digest-verified records from every sealed source page."""
    base = stage_path(root, generation)
    for index, row in enumerate(manifest["pages"]):
        expected = f"pages/{index:08d}.json.gz"
        if not isinstance(row, dict) or row.get("path") != expected:
            raise ValueError("OAI generation page order is invalid")
        path = base / expected
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ValueError(f"OAI generation page is missing: {path.name}") from error
        if len(content) != row.get("bytes") or hashlib.sha256(
            content
        ).hexdigest() != row.get("sha256"):
            raise ValueError(f"OAI generation page digest is invalid: {path.name}")
        payload = read_page(content, path.name)
        records = payload.get("records")
        if (
            payload.get("schema_version") != 1
            or payload.get("generation") != generation
            or payload.get("page") != index
            or payload.get("response_date") != row.get("response_date")
            or not isinstance(records, list)
            or len(records) != row.get("records")
        ):
            raise ValueError(f"OAI generation page contract is invalid: {path.name}")
        if sum(
            isinstance(record, dict) and record.get("deleted") is True
            for record in records
        ) != row.get("tombstones"):
            raise ValueError(f"OAI generation tombstones are invalid: {path.name}")
        yield from records


def open_store(path: Path) -> sqlite3.Connection:
    """Open the bounded-memory event store used during one conversion."""
    database = sqlite3.connect(path)
    database.execute(
        """CREATE TABLE events (
        id TEXT PRIMARY KEY,
        stamp TEXT NOT NULL,
        seq INTEGER NOT NULL,
        deleted INTEGER NOT NULL,
        month TEXT,
        paper TEXT
        )"""
    )
    return database


def index_store(database: sqlite3.Connection) -> None:
    """Index active month routes after bulk event insertion completes."""
    database.execute(
        "CREATE INDEX event_month ON events(month, id) WHERE deleted=0"
    )
    database.commit()


def add_event(
    database: sqlite3.Connection, record: object, seq: int, rules: dict
) -> None:
    """Idempotently retain the newest event for one arXiv identifier."""
    if not isinstance(record, dict):
        raise ValueError("OAI generation record is not an object")
    try:
        identifier = paper_id(clean_text(record.get("id"), "id").lower())
    except ValueError as error:
        raise ValueError("Archive public paper text is invalid") from error
    stamp = event_stamp(record.get("datestamp"))
    deleted = record.get("deleted") is True
    paper = (
        None if deleted else compact_paper(scope_paper(normalize_paper(record), rules))
    )
    month = None if paper is None else month_key(paper["published"])
    body = (
        None
        if paper is None
        else json.dumps(paper, ensure_ascii=False, separators=(",", ":"))
    )
    database.execute(
        """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          stamp=excluded.stamp, seq=excluded.seq, deleted=excluded.deleted,
          month=excluded.month, paper=excluded.paper
        WHERE excluded.stamp > events.stamp
           OR (excluded.stamp = events.stamp AND excluded.seq > events.seq)""",
        (identifier, stamp, seq, deleted, month, body),
    )


def fill_store(
    database: sqlite3.Connection,
    root: Path,
    generation: str,
    manifest: dict,
    rules: dict,
    start_seq: int = 0,
) -> int:
    """Stream one sealed generation into its disk-backed event index."""
    records = 0
    tombstones = 0
    for seq, record in enumerate(
        page_records(root, generation, manifest), start=start_seq
    ):
        add_event(database, record, seq, rules)
        records += 1
        tombstones += isinstance(record, dict) and record.get("deleted") is True
        if records % 10_000 == 0:
            database.commit()
    database.commit()
    if records != manifest["record_count"] or tombstones != manifest["tombstone_count"]:
        raise ValueError("OAI generation record totals are invalid")
    return start_seq + records


def active_months(database: sqlite3.Connection) -> list[str]:
    """Return publication months changed by active OAI records."""
    return [
        row[0]
        for row in database.execute(
            "SELECT DISTINCT month FROM events WHERE deleted=0 ORDER BY month"
        )
    ]


def active_routes(database: sqlite3.Connection) -> dict[str, str]:
    """Map each active identifier to its corrected publication month."""
    return {
        identifier: month
        for identifier, month in database.execute(
            "SELECT id, month FROM events WHERE deleted=0 ORDER BY id"
        )
    }


def find_moves(
    ledger: sqlite3.Connection,
    routes: dict[str, str],
    tombstones: set[str],
) -> tuple[set[str], set[str]]:
    """Find prior shard routes changed or removed by active events."""
    moved: set[str] = set()
    months: set[str] = set()
    rows = ledger.execute("SELECT id, month FROM events WHERE deleted=0 ORDER BY id")
    for identifier, month in rows:
        target = routes.get(identifier)
        if identifier in tombstones:
            months.add(month)
        elif target is not None and target != month:
            moved.add(identifier)
            months.add(month)
    return moved, months


def tombstone_ids(database: sqlite3.Connection) -> set[str]:
    """Return identifiers removed by the sealed generation."""
    return {row[0] for row in database.execute("SELECT id FROM events WHERE deleted=1")}


def month_events(database: sqlite3.Connection, month: str) -> dict[str, dict]:
    """Load one bounded month of classified active upserts."""
    return {
        identifier: json.loads(body)
        for identifier, body in database.execute(
            "SELECT id, paper FROM events WHERE deleted=0 AND month=? ORDER BY id",
            (month,),
        )
    }


def rescore_paper(paper: dict, rules: dict) -> dict:
    """Reapply the current policy without retaining old derived fields."""
    source = {key: paper.get(key) for key in PAPER_FIELDS}
    return compact_paper(scope_paper(normalize_paper(source), rules))


def merge_month(
    root: Path,
    month: str,
    incoming: dict[str, dict],
    removals: set[str],
    rules: dict,
) -> bool:
    """Apply one deterministic group of upserts and tombstones."""
    path = root / f"{month}.json.gz"
    prior = read_shard(path) if path.is_file() else None
    prior_papers = prior["papers"] if prior else []
    papers = {paper["id"]: compact_paper(paper) for paper in prior_papers}
    changed = prior is not None and list(papers.values()) != prior_papers
    for identifier in sorted(removals & papers.keys()):
        del papers[identifier]
        changed = True
    for identifier, paper in incoming.items():
        saved = papers.get(identifier)
        if saved != paper:
            papers[identifier] = paper
            changed = True
    policy_changed = (
        prior is not None and prior.get("policy_version") != rules["version"]
    )
    if policy_changed:
        papers = {
            identifier: rescore_paper(paper, rules)
            for identifier, paper in papers.items()
        }
        changed = True
    if not changed and prior is not None:
        return False
    ordered = [papers[identifier] for identifier in sorted(papers)]
    payload = {
        "schema_version": 1,
        "policy_version": rules["version"],
        "month": month,
        "days": prior.get("days", []) if prior else [],
        "counts": {"all": len(ordered), **scope_counts(ordered)},
        "papers": ordered,
    }
    write_shard(root, payload)
    return True


def check_remote(
    root: Path,
    manifest: dict,
    months: list[str],
    tombstones: set[str],
) -> None:
    """Refuse mutations that would overwrite an unstaged remote shard."""
    remote = {
        row["month"]
        for row in manifest.get("shards", [])
        if not (root / row.get("path", "")).is_file()
    }
    if remote and (months or tombstones):
        raise ValueError("OAI updates require all archive months locally")


def batch_name(generations: list[str]) -> str:
    """Bind a recoverable merge marker to one ordered generation batch."""
    if (
        not generations
        or len(generations) != len(set(generations))
        or not all(isinstance(item, str) and item for item in generations)
    ):
        raise ValueError("OAI generation batch is invalid")
    if len(generations) == 1:
        return generations[0]
    body = json.dumps(generations, separators=(",", ":")).encode()
    return f"batch-{hashlib.sha256(body).hexdigest()[:16]}"


def merge_generations(
    harvest_root: Path,
    generations: list[str],
    archive_root: Path,
    rules: dict,
) -> dict:
    """Convert ordered sealed harvests through one bounded event store."""
    marker = batch_name(generations)
    manifests = [
        (generation, read_generation(harvest_root, generation))
        for generation in generations
    ]
    archive_root.mkdir(parents=True, exist_ok=True)
    if migrate_archive(archive_root):
        write_manifest(archive_root)
    prior = read_manifest(archive_root)
    recovering = merge_path(archive_root).exists()
    required = ledger_needed(archive_root)
    if not recovering:
        check_ledger(archive_root, prior)
    start_merge(archive_root, marker, required)
    ledger = open_ledger(archive_root)
    with tempfile.TemporaryDirectory(dir=archive_root) as directory:
        database = open_store(Path(directory) / "events.sqlite")
        try:
            sequence = 0
            for generation, manifest in manifests:
                sequence = fill_store(
                    database,
                    harvest_root,
                    generation,
                    manifest,
                    rules,
                    sequence,
                )
            filter_events(database, ledger)
            index_store(database)
            routes = active_routes(database)
            months = active_months(database)
            tombstones = tombstone_ids(database)
            check_remote(archive_root, prior, months, tombstones)
            moved, old_months = find_moves(ledger, routes, tombstones)
            removals = tombstones | moved
            targets = set(months)
            targets.update(old_months)
            for month in sorted(targets):
                merge_month(
                    archive_root,
                    month,
                    month_events(database, month),
                    removals,
                    rules,
                )
            result = write_manifest(archive_root)
            save_events(database, ledger)
            check_ledger(archive_root, result, active=True)
        finally:
            database.close()
            ledger.close()
    finish_merge(archive_root)
    return result


def merge_generation(
    harvest_root: Path,
    generation: str,
    archive_root: Path,
    rules: dict,
) -> dict:
    """Convert one sealed harvest into cloud-compatible archive shards."""
    return merge_generations(harvest_root, [generation], archive_root, rules)
