"""Preserve and validate durable OAI event ordering for archive mutations."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from arxivid import paper_id
from archive import MANIFEST_NAME, read_shard
from files import atomic_write_text


LEDGER_NAME = "events.sqlite"
MERGE_NAME = "merge.json"
EVENT_COLS = [
    ("id", "TEXT", 0, 1),
    ("stamp", "TEXT", 1, 0),
    ("deleted", "INTEGER", 1, 0),
    ("month", "TEXT", 0, 0),
]
META_COLS = [("key", "TEXT", 0, 1), ("value", "TEXT", 1, 0)]


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


def merge_path(root: Path) -> Path:
    """Return the durable in-progress merge marker."""
    return root / MERGE_NAME


def ledger_needed(root: Path) -> bool:
    """Return whether this archive has committed durable source state."""
    return (root / MANIFEST_NAME).is_file()


def start_merge(root: Path, generation: str, required: bool) -> bool:
    """Start or resume one recoverable multi-shard mutation."""
    path = merge_path(root)
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Archive merge marker is invalid") from error
        if (
            not isinstance(saved, dict)
            or set(saved) != {"schema_version", "generation", "ledger_required"}
            or saved.get("schema_version") != 1
            or saved.get("generation") != generation
            or not isinstance(saved.get("ledger_required"), bool)
        ):
            raise ValueError("Another archive merge is incomplete")
        required = saved["ledger_required"]
        if required and not (root / LEDGER_NAME).is_file():
            raise ValueError("Archive event ledger is missing")
        return required
    marker = {
        "schema_version": 1,
        "generation": generation,
        "ledger_required": required,
    }
    atomic_write_text(path, json.dumps(marker, sort_keys=True) + "\n")
    return required


def finish_merge(root: Path) -> None:
    """Commit a completed multi-shard mutation by removing its marker."""
    try:
        merge_path(root).unlink()
    except OSError as error:
        raise ValueError("Archive merge marker could not be cleared") from error


def table_cols(database: sqlite3.Connection, table: str) -> list[tuple]:
    """Return one SQLite table's ordered public column contract."""
    return [
        (row[1], row[2], row[3], row[5])
        for row in database.execute(f"PRAGMA table_info({table})")
    ]


def check_schema(database: sqlite3.Connection) -> None:
    """Require the exact supported ledger schema and version."""
    if database.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise ValueError("Archive event ledger integrity check failed")
    tables = database.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    if tables != [("events",), ("meta",)]:
        raise ValueError("Archive event ledger schema is invalid")
    if (
        table_cols(database, "events") != EVENT_COLS
        or table_cols(database, "meta") != META_COLS
    ):
        raise ValueError("Archive event ledger schema is invalid")
    if database.execute("SELECT key, value FROM meta ORDER BY key").fetchall() != [
        ("schema_version", "1")
    ]:
        raise ValueError("Archive event ledger version is invalid")


def load_papers(database: sqlite3.Connection, root: Path, shards: list) -> None:
    """Load exact archived identity routes into a temporary comparison table."""
    database.execute(
        "CREATE TEMP TABLE papers (id TEXT PRIMARY KEY, month TEXT NOT NULL)"
    )
    for row in shards:
        path = root / row.get("path", "")
        if not path.is_file():
            raise ValueError("Archive checkpoint shard is missing")
        database.executemany(
            "INSERT INTO papers VALUES (?, ?)",
            ((paper["id"], row["month"]) for paper in read_shard(path)["papers"]),
        )


def valid_event(
    identifier: object, stamp: object, deleted: object, month: object
) -> bool:
    """Check one normalized ledger row without trusting SQLite affinity."""
    try:
        valid_id = paper_id(identifier) == identifier
        valid_stamp = event_stamp(stamp) == stamp
    except (TypeError, ValueError):
        return False
    return (
        valid_id
        and valid_stamp
        and deleted in {0, 1}
        and (deleted == 1) == (month is None)
    )


def check_rows(database: sqlite3.Connection) -> None:
    """Validate every durable event row's identity and ordering fields."""
    rows = database.execute("SELECT id, stamp, deleted, month FROM events ORDER BY id")
    if any(not valid_event(*row) for row in rows):
        raise ValueError("Archive event ledger row is invalid")


def check_match(database: sqlite3.Connection) -> None:
    """Require exact agreement between active events and public paper routes."""
    missing = database.execute(
        """SELECT 1 FROM papers p LEFT JOIN events e ON e.id=p.id
        WHERE e.id IS NULL OR e.deleted!=0 OR e.month!=p.month LIMIT 1"""
    ).fetchone()
    extra = database.execute(
        """SELECT 1 FROM events e LEFT JOIN papers p ON p.id=e.id
        WHERE e.deleted=0 AND (p.id IS NULL OR p.month!=e.month) LIMIT 1"""
    ).fetchone()
    if missing is not None or extra is not None:
        raise ValueError("Archive event ledger disagrees with public shards")


def check_ledger(root: Path, manifest: dict, *, active: bool = False) -> None:
    """Verify durable OAI ordering against every archived paper identity."""
    if merge_path(root).exists() and not active:
        raise ValueError("Archive merge is incomplete")
    path = root / LEDGER_NAME
    shards = manifest.get("shards", [])
    if not path.is_file():
        if ledger_needed(root) or shards:
            raise ValueError("Archive event ledger is missing")
        return
    database = None
    try:
        database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        check_schema(database)
        load_papers(database, root, shards)
        check_rows(database)
        check_match(database)
    except sqlite3.DatabaseError as error:
        raise ValueError("Archive event ledger is invalid") from error
    finally:
        if database is not None:
            database.close()


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
