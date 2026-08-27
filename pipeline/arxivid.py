#!/usr/bin/env python3
"""Validate canonical modern and historical arXiv identifiers."""

from __future__ import annotations

import re


MODERN_ID = re.compile(r"^\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}$")
LEGACY_ID = re.compile(r"^([a-z][a-z.-]*)/\d{2}(?:0[1-9]|1[0-2])\d{3}$")
LEGACY_ARCHIVES = frozenset(
    {
        "acc-phys",
        "adap-org",
        "alg-geom",
        "ao-sci",
        "astro-ph",
        "atom-ph",
        "bayes-an",
        "chao-dyn",
        "chem-ph",
        "cmp-lg",
        "comp-gas",
        "cond-mat",
        "cs",
        "dg-ga",
        "funct-an",
        "gr-qc",
        "hep-ex",
        "hep-lat",
        "hep-ph",
        "hep-th",
        "math",
        "math-ph",
        "mtrl-th",
        "nlin",
        "nucl-ex",
        "nucl-th",
        "patt-sol",
        "physics",
        "plasm-ph",
        "q-alg",
        "q-bio",
        "quant-ph",
        "solv-int",
        "stat",
        "supr-con",
    }
)


def paper_id(value: object) -> str:
    """Require one canonical modern or known historical arXiv identifier."""
    if isinstance(value, str) and MODERN_ID.fullmatch(value):
        return value
    legacy = LEGACY_ID.fullmatch(value) if isinstance(value, str) else None
    if legacy and legacy.group(1) in LEGACY_ARCHIVES:
        return value
    raise ValueError("Invalid canonical arXiv identifier")


def valid_id(value: object) -> bool:
    """Report whether a value is a canonical public arXiv identifier."""
    try:
        paper_id(value)
    except ValueError:
        return False
    return True
