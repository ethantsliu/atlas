#!/usr/bin/env python3
"""Validate and combine OAI server timestamps."""

from __future__ import annotations

from datetime import date, datetime


def clean_date(value: object) -> str:
    """Require one UTC OAI response timestamp."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("OAI page is missing a UTC responseDate")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("OAI page has an invalid responseDate") from error
    if parsed.utcoffset() is None:
        raise ValueError("OAI page responseDate must include UTC")
    return value


def newest_date(prior: str | None, current: str) -> str:
    """Keep a monotonic watermark across server clock skew."""
    current = clean_date(current)
    if prior is None:
        return current
    prior = clean_date(prior)
    prior_time = datetime.fromisoformat(prior.removesuffix("Z") + "+00:00")
    current_time = datetime.fromisoformat(current.removesuffix("Z") + "+00:00")
    return current if current_time > prior_time else prior


def exact_day(value: object, field: str) -> str | None:
    """Validate one optional exact calendar day."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} day is invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} day is invalid") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field} day is invalid")
    return value


def first_date(manifest: dict) -> str:
    """Return the first response timestamp from one sealed query."""
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
        raise ValueError("Corpus manifest has no first responseDate")
    return clean_date(pages[0].get("response_date"))


def coverage_day(manifest: dict, generation: str) -> str:
    """Return the exact conservative day covered by one sealed query."""
    if generation.startswith("history-"):
        query = manifest.get("query")
        value = query.get("until") if isinstance(query, dict) else None
    else:
        value = first_date(manifest)[:10]
    if value is None:
        raise ValueError("Corpus generation has no coverage day")
    return exact_day(value, "Corpus generation coverage")
