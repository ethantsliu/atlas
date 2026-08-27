#!/usr/bin/env python3
"""Checkpoint serial OAI pages without deriving research metadata."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from files import atomic_write_bytes, atomic_write_text
from oai import PREFIX, OaiError


SCHEMA_VERSION = 1
GENERATION = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
HISTORY_START = 2005
HISTORY_FIRST = "2005-09-16"


class PageLike(Protocol):
    """OAI page fields required by the durable coordinator."""

    records: tuple[dict, ...]
    token: str | None
    expires: str | None
    response_date: str | None
    cursor: int | None
    total: int | None


class ClientLike(Protocol):
    """Serial page iterator supplied by the OAI transport."""

    def pages(
        self,
        start: str | None = None,
        end: str | None = None,
        token: str | None = None,
    ): ...


def stage_path(root: Path, generation: str) -> Path:
    """Return a traversal-safe staging directory for one generation."""
    if not GENERATION.fullmatch(generation):
        raise ValueError("Harvest generation is invalid")
    return root / "stage" / generation


def state_path(root: Path, generation: str) -> Path:
    """Return the atomic checkpoint path for one generation."""
    return stage_path(root, generation) / "state.json"


def page_path(root: Path, generation: str, index: int) -> Path:
    """Return the deterministic asset path for one source page."""
    if index < 0:
        raise ValueError("Harvest page index cannot be negative")
    return stage_path(root, generation) / "pages" / f"{index:08d}.json.gz"


def clean_date(value: object) -> str:
    """Require the UTC server response timestamp used as a watermark."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("OAI page is missing a UTC responseDate")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("OAI page has an invalid responseDate") from error
    if parsed.utcoffset() is None:
        raise ValueError("OAI page responseDate must include UTC")
    return value


def page_date(page: PageLike) -> str:
    """Read responseDate without substituting record or local timestamps."""
    return clean_date(getattr(page, "response_date", None))


def clean_day(value: object, field: str) -> str | None:
    """Require one optional canonical OAI calendar day."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Harvest {field} date is invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Harvest {field} date is invalid") from error
    if parsed.isoformat() != value:
        raise ValueError(f"Harvest {field} date is invalid")
    return value


def check_history(value: object) -> dict:
    """Validate the durable annual all-history cursor."""
    if not isinstance(value, dict):
        raise ValueError("Corpus history cursor is invalid")
    next_year = value.get("next_year")
    through = value.get("through_year")
    complete = value.get("complete")
    if (
        not isinstance(next_year, int)
        or isinstance(next_year, bool)
        or next_year < HISTORY_START
        or through is not None
        and (
            not isinstance(through, int)
            or isinstance(through, bool)
            or through < HISTORY_START
            or next_year > through + 1
        )
        or not isinstance(complete, bool)
        or complete != (through is not None and next_year > through)
    ):
        raise ValueError("Corpus history cursor is invalid")
    return value


def plan_history(history: dict, current_year: int) -> tuple[dict, str, str, str]:
    """Plan one deterministic annual OAI datestamp window."""
    history = check_history(history)
    through = history["through_year"] or current_year
    year = history["next_year"]
    if year > through:
        raise ValueError("Corpus history cursor advanced beyond its horizon")
    planned = {**history, "through_year": through}
    start = HISTORY_FIRST if year == HISTORY_START else f"{year:04d}-01-01"
    return planned, f"history-{year}", start, f"{year:04d}-12-31"


def advance_history(history: dict, generation: str) -> dict:
    """Advance exactly one sealed annual history window."""
    history = check_history(history)
    if not generation.startswith("history-") or history["through_year"] is None:
        raise ValueError("Corpus history generation is invalid")
    try:
        year = int(generation.removeprefix("history-"))
    except ValueError as error:
        raise ValueError("Corpus history generation is invalid") from error
    if year != history["next_year"]:
        raise ValueError("Corpus history generation is out of order")
    next_year = year + 1
    return check_history(
        {
            **history,
            "next_year": next_year,
            "complete": next_year > history["through_year"],
        }
    )


def new_state(generation: str, start: str | None, end: str | None = None) -> dict:
    """Create the initial checkpoint before making a network request."""
    if not GENERATION.fullmatch(generation):
        raise ValueError("Harvest generation is invalid")
    start = clean_day(start, "start")
    end = clean_day(end, "end")
    if start is not None and end is not None and start > end:
        raise ValueError("Harvest start date follows its end date")
    return {
        "schema_version": SCHEMA_VERSION,
        "generation": generation,
        "status": "running",
        "query": {"metadata_prefix": PREFIX, "from": start, "until": end},
        "next_token": None,
        "token_expires": None,
        "source_total": None,
        "watermark": None,
        "page_count": 0,
        "record_count": 0,
        "tombstone_count": 0,
        "pages": [],
    }


def check_state(state: object, generation: str) -> dict:
    """Validate a checkpoint before trusting its opaque continuation token."""
    if not isinstance(state, dict):
        raise ValueError("Harvest checkpoint is not an object")
    if (
        state.get("schema_version") != SCHEMA_VERSION
        or state.get("generation") != generation
        or state.get("status") not in {"running", "complete"}
        or not isinstance(state.get("query"), dict)
        or state["query"].get("metadata_prefix") != PREFIX
        or not isinstance(state.get("pages"), list)
    ):
        raise ValueError("Harvest checkpoint contract is invalid")
    counts = ("page_count", "record_count", "tombstone_count")
    if any(
        not isinstance(state.get(key), int)
        or isinstance(state.get(key), bool)
        or state[key] < 0
        for key in counts
    ):
        raise ValueError("Harvest checkpoint counts are invalid")
    if state["page_count"] != len(state["pages"]):
        raise ValueError("Harvest checkpoint page count is invalid")
    token = state.get("next_token")
    if token is not None and (not isinstance(token, str) or not token):
        raise ValueError("Harvest checkpoint token is invalid")
    if state["status"] == "complete" and token is not None:
        raise ValueError("Complete harvest checkpoint retains a token")
    if state["page_count"] and state["status"] == "running" and token is None:
        raise ValueError("Running harvest checkpoint lost its token")
    watermark = state.get("watermark")
    if watermark is not None:
        clean_date(watermark)
    expiry = state.get("token_expires")
    if expiry is not None:
        clean_date(expiry)
    source_total = state.get("source_total")
    if source_total is not None and (
        not isinstance(source_total, int)
        or isinstance(source_total, bool)
        or source_total < 0
    ):
        raise ValueError("Harvest source total is invalid")
    start = clean_day(state["query"].get("from"), "start")
    end = clean_day(state["query"].get("until"), "end")
    if start is not None and end is not None and start > end:
        raise ValueError("Harvest checkpoint date range is invalid")
    return state


def read_state(root: Path, generation: str) -> dict | None:
    """Read a prior checkpoint, returning none for a new generation."""
    path = state_path(root, generation)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Harvest checkpoint is unreadable") from error
    return check_state(value, generation)


def write_state(root: Path, generation: str, state: dict) -> None:
    """Atomically replace the continuation checkpoint."""
    check_state(state, generation)
    atomic_write_text(
        state_path(root, generation),
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
    )


def page_bytes(payload: dict) -> bytes:
    """Serialize one immutable source page reproducibly."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return gzip.compress(body, compresslevel=9, mtime=0)


def save_page(
    root: Path,
    generation: str,
    index: int,
    page: PageLike,
) -> dict:
    """Atomically stage one complete page before advancing its token."""
    response_date = page_date(page)
    records = list(page.records)
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("OAI page records must be objects")
    if any(not record.get("id") for record in records):
        raise ValueError("OAI page record is missing its identifier")
    tombstones = sum(record.get("deleted") is True for record in records)
    cursor = getattr(page, "cursor", None)
    total = getattr(page, "total", None)
    token = page.token
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generation": generation,
        "page": index,
        "response_date": response_date,
        "records": records,
    }
    content = page_bytes(payload)
    path = page_path(root, generation, index)
    atomic_write_bytes(path, content)
    return {
        "page": index,
        "path": str(path.relative_to(stage_path(root, generation))),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "records": len(records),
        "tombstones": tombstones,
        "response_date": response_date,
        "cursor": cursor,
        "source_total": total,
        "token_sha256": hashlib.sha256(token.encode()).hexdigest() if token else None,
    }


def read_page(content: bytes, name: str) -> dict:
    """Read one staged page for final integrity validation."""
    try:
        return json.loads(gzip.decompress(content))
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Harvest page is unreadable: {name}") from error


def check_page(
    root: Path,
    generation: str,
    index: int,
    row: object,
) -> tuple[int, int, str, int | None, int | None, str | None]:
    """Verify one staged page and return its reconciled totals."""
    expected_path = f"pages/{index:08d}.json.gz"
    if (
        not isinstance(row, dict)
        or row.get("page") != index
        or row.get("path") != expected_path
    ):
        raise ValueError("Harvest page index is invalid")
    path = stage_path(root, generation) / expected_path
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(f"Harvest page is missing: {path.name}") from error
    if hashlib.sha256(content).hexdigest() != row.get("sha256") or len(
        content
    ) != row.get("bytes"):
        raise ValueError(f"Harvest page digest is invalid: {path.name}")
    payload = read_page(content, path.name)
    records = payload.get("records")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("generation") != generation
        or payload.get("page") != index
        or payload.get("response_date") != row.get("response_date")
        or not isinstance(records, list)
    ):
        raise ValueError(f"Harvest page contract is invalid: {path.name}")
    if not all(isinstance(record, dict) and record.get("id") for record in records):
        raise ValueError(f"Harvest page records are invalid: {path.name}")
    tombstones = sum(record.get("deleted") is True for record in records)
    if len(records) != row.get("records"):
        raise ValueError(f"Harvest page counts are invalid: {path.name}")
    if tombstones != row.get("tombstones"):
        raise ValueError(f"Harvest tombstone count is invalid: {path.name}")
    cursor = row.get("cursor")
    total = row.get("source_total")
    token_hash = row.get("token_sha256")
    for value, field in ((cursor, "cursor"), (total, "source total")):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ValueError(f"Harvest page {field} is invalid: {path.name}")
    if token_hash is not None and (
        not isinstance(token_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", token_hash)
    ):
        raise ValueError(f"Harvest page token digest is invalid: {path.name}")
    return (
        len(records),
        tombstones,
        clean_date(row.get("response_date")),
        cursor,
        total,
        token_hash,
    )


def sum_page(summary: dict, checked: tuple) -> dict:
    """Fold one verified page into source-order completeness totals."""
    records, tombstones, response_date, cursor, total, token_hash = checked
    if cursor is not None and cursor != summary["records"]:
        raise ValueError("Harvest page cursor did not advance continuously")
    source_total = summary["source_total"]
    if total is not None:
        if source_total is not None and total != source_total:
            raise ValueError("Harvest source total changed between pages")
        source_total = total
    if source_total is not None and summary["records"] + records > source_total:
        raise ValueError("Harvest record count exceeds its source total")
    token_hashes = summary["token_hashes"]
    if token_hash is not None:
        if token_hash in token_hashes:
            raise ValueError("Harvest resumption token repeated")
        token_hashes = token_hashes | {token_hash}
    watermark = summary["watermark"]
    if watermark is not None and response_date < watermark:
        raise ValueError("Harvest page response dates are not monotonic")
    return {
        "records": summary["records"] + records,
        "tombstones": summary["tombstones"] + tombstones,
        "watermark": response_date,
        "source_total": source_total,
        "token_hashes": token_hashes,
    }


def check_totals(state: dict, summary: dict) -> None:
    """Reconcile folded page totals with their durable checkpoint."""
    if (
        summary["records"] != state["record_count"]
        or summary["tombstones"] != state["tombstone_count"]
    ):
        raise ValueError("Harvest checkpoint totals are invalid")
    if summary["watermark"] != state["watermark"]:
        raise ValueError("Harvest checkpoint watermark is invalid")
    if summary["source_total"] != state.get("source_total"):
        raise ValueError("Harvest checkpoint source total is invalid")


def check_end(state: dict, summary: dict) -> None:
    """Validate terminal completeness or the active continuation token."""
    last = state["pages"][-1] if state["pages"] else {}
    last_hash = last.get("token_sha256")
    has_hash = "token_sha256" in last
    if state["status"] == "complete":
        if has_hash and last_hash is not None:
            raise ValueError("Complete harvest checkpoint retains a page token")
        source_total = summary["source_total"]
        if source_total is not None and summary["records"] != source_total:
            raise ValueError("Completed harvest does not match its source total")
    elif state.get("next_token") is not None and has_hash:
        expected = hashlib.sha256(state["next_token"].encode()).hexdigest()
        if last_hash != expected:
            raise ValueError("Harvest checkpoint token does not match its page")


def check_stage(root: Path, generation: str) -> dict:
    """Reconcile every staged byte before sealing a generation."""
    state = read_state(root, generation)
    if state is None:
        raise ValueError("Harvest checkpoint does not exist")
    summary = {
        "records": 0,
        "tombstones": 0,
        "watermark": None,
        "source_total": None,
        "token_hashes": set(),
    }
    for index, row in enumerate(state["pages"]):
        summary = sum_page(summary, check_page(root, generation, index, row))
    check_totals(state, summary)
    check_end(state, summary)
    return state


def page_meta(state: dict, page: PageLike) -> tuple[str | None, int | None]:
    """Validate page progression and return its next token and source total."""
    token = page.token
    if token is not None and (not isinstance(token, str) or not token):
        raise ValueError("OAI page token is invalid")
    if page.expires is not None:
        clean_date(page.expires)
    cursor = getattr(page, "cursor", None)
    total = getattr(page, "total", None)
    for value, field in ((cursor, "cursor"), (total, "source total")):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ValueError(f"OAI page {field} is invalid")
    if cursor is not None and cursor != state["record_count"]:
        raise ValueError("OAI page cursor did not advance continuously")
    source_total = state.get("source_total")
    if total is not None:
        if source_total is not None and total != source_total:
            raise ValueError("OAI source total changed between pages")
        source_total = total
    next_count = state["record_count"] + len(page.records)
    if source_total is not None and next_count > source_total:
        raise ValueError("OAI record count exceeds its source total")
    token_hash = hashlib.sha256(token.encode()).hexdigest() if token else None
    prior_hashes = {row.get("token_sha256") for row in state["pages"]}
    if token is not None and (
        token == state.get("next_token") or token_hash in prior_hashes
    ):
        raise OaiError("badResumptionToken", "resumption token repeated")
    if token is None and source_total is not None and next_count != source_total:
        raise ValueError("Terminal OAI page does not match its source total")
    return token, source_total


def seal_stage(root: Path, generation: str) -> dict:
    """Publish the completed generation manifest last and atomically."""
    state = check_stage(root, generation)
    if state["status"] != "complete" or state["next_token"] is not None:
        raise ValueError("Cannot seal an incomplete harvest")
    manifest = {key: value for key, value in state.items() if key != "next_token"}
    manifest["sealed"] = True
    atomic_write_text(
        stage_path(root, generation) / "index.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def gc_stages(root: Path, keep: set[str]) -> list[str]:
    """Delete only verified sealed stages outside the durable reference set."""
    stage = root / "stage"
    removed = []
    if not stage.is_dir():
        return removed
    for path in sorted(stage.iterdir()):
        if path.is_symlink():
            raise ValueError("Harvest stage cannot be a symbolic link")
        if not path.is_dir():
            continue
        if path.name in keep:
            continue
        state = read_state(root, path.name)
        if state is None or state["status"] != "complete":
            continue
        check_stage(root, path.name)
        manifest = {key: value for key, value in state.items() if key != "next_token"}
        manifest["sealed"] = True
        try:
            saved = json.loads((path / "index.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Harvest sealed manifest is unreadable") from error
        if saved != manifest or path.parent != stage:
            raise ValueError("Harvest sealed manifest is invalid")
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


def run_harvest(
    root: Path,
    generation: str,
    client: ClientLike,
    *,
    start: str | None = None,
    end: str | None = None,
    max_pages: int | None = None,
) -> dict:
    """Fetch serial pages, checkpoint each, and seal only a terminal list."""
    if max_pages is not None and max_pages < 1:
        raise ValueError("Harvest page limit must be positive")
    state = read_state(root, generation)
    if state is None:
        state = new_state(generation, start, end)
        write_state(root, generation, state)
    elif state["query"].get("from") != start or state["query"].get("until") != end:
        raise ValueError("Harvest resume query does not match its checkpoint")
    if state["status"] == "complete":
        return seal_stage(root, generation)

    prior_token = state["next_token"]
    pages = client.pages(
        start=start if prior_token is None else None,
        end=end if prior_token is None else None,
        token=prior_token,
    )
    completed = 0
    for page in pages:
        index = state["page_count"]
        token, source_total = page_meta(state, page)
        response_date = page_date(page)
        if state["watermark"] is not None and response_date < state["watermark"]:
            raise ValueError("OAI responseDate moved backwards")
        row = save_page(root, generation, index, page)
        state = {
            **state,
            "status": "running" if token else "complete",
            "next_token": token,
            "token_expires": page.expires,
            "source_total": source_total,
            "watermark": row["response_date"],
            "page_count": index + 1,
            "record_count": state["record_count"] + row["records"],
            "tombstone_count": state["tombstone_count"] + row["tombstones"],
            "pages": [*state["pages"], row],
        }
        write_state(root, generation, state)
        completed += 1
        if state["status"] == "complete":
            return seal_stage(root, generation)
        if max_pages is not None and completed >= max_pages:
            return state
    raise RuntimeError("OAI page sequence ended without a terminal response")
