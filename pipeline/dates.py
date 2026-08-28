#!/usr/bin/env python3
"""Validate and combine OAI server timestamps."""

from __future__ import annotations

from datetime import datetime


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
