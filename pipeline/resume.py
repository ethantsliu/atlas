#!/usr/bin/env python3
"""Recover bounded OAI harvests without weakening their checkpoints."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from harvest import clean_date, read_state, run_harvest, stage_path
from oai import OaiError


EXPIRY_MARGIN = timedelta(minutes=15)


def parse_time(value: str) -> datetime:
    """Parse one OAI UTC timestamp."""
    clean_date(value)
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def expiry_near(state: dict | None, now: datetime) -> bool:
    """Stop before an opaque daily token becomes unusable."""
    if state is None or state.get("next_token") is None:
        return False
    expiry = state.get("token_expires")
    return expiry is not None and now + EXPIRY_MARGIN >= parse_time(expiry)


def token_expired(state: dict | None, now: datetime) -> bool:
    """Detect an unusable active continuation token."""
    if state is None or state.get("next_token") is None:
        return False
    expiry = state.get("token_expires")
    return expiry is not None and now >= parse_time(expiry)


def reset_stage(root: Path, generation: str, state: dict) -> None:
    """Restart an unsealed expired query from its safe original boundary."""
    if state.get("status") != "running" or state.get("next_token") is None:
        raise ValueError("Only an active expired harvest can restart")
    path = stage_path(root, generation)
    if not path.is_dir() or path.parent != root / "stage":
        raise ValueError("Expired harvest stage is missing")
    shutil.rmtree(path)


def next_page(
    root: Path,
    generation: str,
    client,
    start: str | None,
    end: str | None,
) -> tuple[dict | None, bool]:
    """Fetch one page or restart a bounded query after a rejected token."""
    try:
        return (
            run_harvest(
                root,
                generation,
                client,
                start=start,
                end=end,
                max_pages=1,
            ),
            False,
        )
    except OaiError as error:
        stale = read_state(root, generation)
        if (
            error.code != "badResumptionToken"
            or stale is None
            or stale.get("next_token") is None
        ):
            raise
        reset_stage(root, generation, stale)
        return None, True
