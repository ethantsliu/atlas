"""Migrate restored OAI stages to the public checkpoint boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path

from files import atomic_write_bytes
from harvest import (
    check_stage,
    page_bytes,
    page_path,
    read_page,
    read_state,
    seal_stage,
    write_state,
)
from scrub import scrub_tree


def scrub_stage(root: Path, generation: str) -> bool:
    """Scrub and rehash one restored durable stage."""
    state = read_state(root, generation)
    if state is None:
        raise ValueError("Harvest checkpoint does not exist")
    rows = []
    changed = False
    for index, row in enumerate(state["pages"]):
        path = page_path(root, generation, index)
        content = path.read_bytes()
        if len(content) != row.get("bytes") or hashlib.sha256(
            content
        ).hexdigest() != row.get("sha256"):
            raise ValueError(f"Harvest page digest is invalid: {path.name}")
        payload = read_page(content, path.name)
        records = payload.get("records")
        if not isinstance(records, list):
            raise ValueError(f"Harvest page contract is invalid: {path.name}")
        cleaned = scrub_tree(records)
        if cleaned != records:
            content = page_bytes({**payload, "records": cleaned})
            atomic_write_bytes(path, content)
            row = {
                **row,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
            changed = True
        rows.append(row)
    if changed:
        state = {**state, "pages": rows}
        write_state(root, generation, state)
        if state["status"] == "complete":
            seal_stage(root, generation)
    check_stage(root, generation)
    return changed
