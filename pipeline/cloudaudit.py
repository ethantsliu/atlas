"""Validate the self-describing physical schema of cloud release assets."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from routes import row_digest


MAGIC = b"ATLASPT1"
SCOPES = {"likely": 0, "possible": 1, "outside": 2}


def valid_asset(path: Path, meta: object) -> bool:
    """Verify one browser asset against its path, size, and digest contract."""
    if not path.is_file() or not isinstance(meta, dict):
        return False
    content = path.read_bytes()
    return (
        meta.get("path") == path.name
        and meta.get("bytes") == len(content)
        and meta.get("sha256") == hashlib.sha256(content).hexdigest()
    )


def point_rows(content: bytes, row: dict, month: str) -> np.ndarray:
    """Validate finite coordinates and return count-bound scope bytes."""
    try:
        count = row["count"]
        magic, saved = struct.unpack("<8sI", content[:12])
        points = np.frombuffer(content[12 : 12 + count * 12], dtype="<f4")
        scopes = np.frombuffer(content[12 + count * 12 :], dtype=np.uint8)
        expected = np.asarray([row["counts"][scope] for scope in SCOPES])
        actual = np.bincount(scopes, minlength=len(SCOPES))
    except (KeyError, TypeError, ValueError, struct.error) as error:
        raise RuntimeError(f"Archive cloud point contract drifted: {month}") from error
    if (
        magic != MAGIC
        or saved != count
        or len(content) != 12 + 13 * count
        or points.size != count * 3
        or not np.isfinite(points).all()
        or np.any(scopes >= len(SCOPES))
        or not np.array_equal(actual, expected)
    ):
        raise RuntimeError(f"Archive cloud point contract drifted: {month}")
    return scopes


def meta_rows(content: str, row: dict, scopes: np.ndarray, month: str) -> list[str]:
    """Validate metadata identity and exact point-scope row alignment."""
    try:
        meta = json.loads(content)
        papers = meta["papers"]
        identifiers = [paper[0] for paper in papers]
        meta_scopes = np.asarray([SCOPES[paper[4]] for paper in papers], dtype=np.uint8)
    except (json.JSONDecodeError, IndexError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Archive cloud metadata coverage drifted: {month}"
        ) from error
    if (
        meta.get("schema_version") != 1
        or meta.get("month") != month
        or meta.get("count") != row["count"]
        or len(papers) != row["count"]
        or any(not isinstance(paper, list) or len(paper) != 5 for paper in papers)
        or any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        )
        or not np.array_equal(meta_scopes, scopes)
        or row.get("row_sha256") != row_digest(identifiers)
    ):
        raise RuntimeError(f"Archive cloud metadata coverage drifted: {month}")
    return identifiers
