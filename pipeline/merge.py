#!/usr/bin/env python3
"""Promote sealed OAI pages into deterministic monthly archive shards."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unicodedata
from datetime import date, datetime, timezone
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
LEDGER_NAME = "events.sqlite"


def iso_date(value: object, field: str) -> str:
    """Normalize one ISO day or timezone-aware timestamp."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"OAI record is missing {field}")
    text = value.strip()
    if len(text) == 10:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as error:
            raise ValueError(f"OAI record has invalid {field}") from error
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"OAI record has invalid {field}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"OAI record {field} lacks a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def event_stamp(value: object) -> str:
    """Normalize source ordering to one lexically comparable UTC form."""
    text = iso_date(value, "datestamp")
    return f"{text}T00:00:00Z" if len(text) == 10 else text


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
    categories = clean_list(record.get("categories"), "categories")
    published = iso_date(record.get("published"), "published")
    updated = iso_date(record.get("updated") or published, "updated")
    primary = record.get("primary_category") or (categories[0] if categories else "")
    if not isinstance(primary, str):
        raise ValueError("OAI record has invalid primary_category")
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": clean_text(record.get("title"), "title"),
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
) -> None:
    """Stream one sealed generation into its disk-backed event index."""
    records = 0
    tombstones = 0
    for seq, record in enumerate(page_records(root, generation, manifest)):
        add_event(database, record, seq, rules)
        records += 1
        tombstones += isinstance(record, dict) and record.get("deleted") is True
        if records % 10_000 == 0:
            database.commit()
    database.commit()
    if records != manifest["record_count"] or tombstones != manifest["tombstone_count"]:
        raise ValueError("OAI generation record totals are invalid")


def open_ledger(root: Path) -> sqlite3.Connection:
    """Open the durable source-order ledger retained in corpus checkpoints."""
    try:
        database = sqlite3.connect(root / LEDGER_NAME)
        database.execute(
            """CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            stamp TEXT NOT NULL,
            deleted INTEGER NOT NULL,
            month TEXT
            )"""
        )
        database.execute(
            """CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
            )"""
        )
        database.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', '1')")
        version = database.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        if version != ("1",):
            raise ValueError("Archive event ledger version is invalid")
        return database
    except sqlite3.DatabaseError as error:
        raise ValueError("Archive event ledger is invalid") from error


def seed_ledger(database: sqlite3.Connection, root: Path) -> None:
    """Bootstrap source ordering from public rows when no ledger exists."""
    if database.execute("SELECT 1 FROM events LIMIT 1").fetchone() is not None:
        return
    for path in sorted(root.glob("????-??.json.gz")):
        for paper in read_shard(path)["papers"]:
            database.execute(
                "INSERT INTO events VALUES (?, ?, 0, ?)",
                (
                    paper["id"],
                    event_stamp(iso_date(paper["updated"], "updated")[:10]),
                    path.name[:7],
                ),
            )
    database.commit()


def filter_events(database: sqlite3.Connection, ledger: sqlite3.Connection) -> None:
    """Discard source events older than the durable per-paper watermark."""
    stale = []
    for identifier, stamp in database.execute(
        "SELECT id, stamp FROM events ORDER BY id"
    ):
        prior = ledger.execute(
            "SELECT stamp FROM events WHERE id=?", (identifier,)
        ).fetchone()
        if prior is not None and stamp < prior[0]:
            stale.append(identifier)
    database.executemany("DELETE FROM events WHERE id=?", [(row,) for row in stale])
    database.commit()


def save_events(database: sqlite3.Connection, ledger: sqlite3.Connection) -> None:
    """Advance durable watermarks after every archive mutation succeeds."""
    ledger.executemany(
        """INSERT INTO events VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          stamp=excluded.stamp, deleted=excluded.deleted, month=excluded.month
        WHERE excluded.stamp >= events.stamp""",
        database.execute(
            "SELECT id, stamp, deleted, month FROM events ORDER BY id"
        ).fetchall(),
    )
    ledger.commit()


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


def find_moves(root: Path, routes: dict[str, str]) -> tuple[set[str], set[str]]:
    """Find active identifiers that must leave an older month shard."""
    moved: set[str] = set()
    months: set[str] = set()
    seen: set[str] = set()
    for path in sorted(root.glob("????-??.json.gz")):
        month = path.name.removesuffix(".json.gz")
        for paper in read_shard(path)["papers"]:
            identifier = paper.get("id")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("Archive paper ID is invalid")
            if identifier in seen:
                raise ValueError("Archive paper IDs are duplicated across months")
            seen.add(identifier)
            target = routes.get(identifier)
            if target is not None and target != month:
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


def merge_generation(
    harvest_root: Path,
    generation: str,
    archive_root: Path,
    rules: dict,
) -> dict:
    """Convert one sealed harvest into cloud-compatible archive shards."""
    manifest = read_generation(harvest_root, generation)
    archive_root.mkdir(parents=True, exist_ok=True)
    migrate_archive(archive_root)
    ledger = open_ledger(archive_root)
    with tempfile.TemporaryDirectory(dir=archive_root) as directory:
        database = open_store(Path(directory) / "events.sqlite")
        try:
            fill_store(database, harvest_root, generation, manifest, rules)
            seed_ledger(ledger, archive_root)
            filter_events(database, ledger)
            routes = active_routes(database)
            months = active_months(database)
            tombstones = tombstone_ids(database)
            prior = read_manifest(archive_root)
            check_remote(archive_root, prior, months, tombstones)
            moved, old_months = find_moves(archive_root, routes)
            removals = tombstones | moved
            targets = set(months)
            targets.update(old_months)
            if tombstones:
                targets.update(
                    path.name.removesuffix(".json.gz")
                    for path in archive_root.glob("????-??.json.gz")
                )
            for month in sorted(targets):
                merge_month(
                    archive_root,
                    month,
                    month_events(database, month),
                    removals,
                    rules,
                )
            save_events(database, ledger)
        finally:
            database.close()
            ledger.close()
    return write_manifest(archive_root)
