"""Small filesystem helpers for publishing complete generated artifacts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Replace a file only after its complete new contents reach disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str) -> None:
    """UTF-8 text counterpart to :func:`atomic_write_bytes`."""
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_copy(source: Path, destination: Path) -> None:
    """Publish a byte-identical copy without exposing a partial file."""
    atomic_write_bytes(destination, source.read_bytes())
