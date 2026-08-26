"""Validate ordered semantic-vector cache rows."""

from __future__ import annotations

import numpy as np


def valid_ids(ids: np.ndarray, expected: np.ndarray) -> bool:
    """Return whether cached node IDs exactly match the ordered input."""
    return (
        ids.ndim == 1
        and len(ids) == len(expected)
        and len({str(node_id) for node_id in ids}) == len(expected)
        and np.array_equal(ids.astype(str), expected.astype(str))
    )


def valid_hashes(hashes: np.ndarray, expected: np.ndarray) -> bool:
    """Return whether every cached row hash matches its semantic input."""
    return (
        hashes.ndim == 1
        and len(hashes) == len(expected)
        and np.array_equal(hashes.astype(str), expected.astype(str))
    )
