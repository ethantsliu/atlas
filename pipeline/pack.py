"""Pack monthly point buffers into stable, digest-bound browser assets."""

from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

import numpy as np

from cloudaudit import SCOPES, point_rows, valid_asset
from files import atomic_write_bytes


PACK_MAGIC = b"ATLASPK1"
PACK_MODE = "month-14-v1"
PACK_MONTHS = 14
EPOCH = 1991 * 12 + 7
PACK_PATH = re.compile(r"p\d{3,}\.bin")


def month_ord(month: str) -> int:
    """Convert one strict calendar month to a stable ordinal."""
    if (
        not isinstance(month, str)
        or len(month) != 7
        or month[4] != "-"
        or not month[:4].isdigit()
        or not month[5:].isdigit()
    ):
        raise ValueError("Point pack month is invalid")
    year = int(month[:4])
    number = int(month[5:])
    if not 1 <= number <= 12:
        raise ValueError("Point pack month is invalid")
    return year * 12 + number - 1


def pack_key(month: str) -> int:
    """Return the immutable fourteen-month bucket for one month."""
    delta = month_ord(month) - EPOCH
    if delta < 0:
        raise ValueError("Point pack month predates arXiv")
    return delta // PACK_MONTHS


def pack_path(key: int) -> str:
    """Name one stable point-pack asset."""
    if not isinstance(key, int) or isinstance(key, bool) or key < 0:
        raise ValueError("Point pack key is invalid")
    return f"p{key:03d}.bin"


def point_parts(root: Path, row: dict) -> tuple[bytes, bytes]:
    """Read and validate one monthly position and scope pair."""
    month = row.get("month")
    meta = row.get("points")
    path = root / meta.get("path", "") if isinstance(meta, dict) else root
    if not isinstance(month, str) or not valid_asset(path, meta):
        raise RuntimeError(f"Point pack source drifted: {month}")
    content = path.read_bytes()
    scopes = point_rows(content, row, month)
    count = row["count"]
    return content[12 : 12 + count * 12], scopes.tobytes()


def pack_bytes(root: Path, rows: list[dict]) -> bytes:
    """Encode ordered monthly points with exactly thirteen bytes per node."""
    positions = bytearray()
    scopes = bytearray()
    count = 0
    for row in rows:
        points, lanes = point_parts(root, row)
        positions.extend(points)
        scopes.extend(lanes)
        count += row["count"]
    return struct.pack("<8sI", PACK_MAGIC, count) + positions + scopes


def asset_meta(path: Path) -> dict:
    """Describe one immutable pack asset."""
    content = path.read_bytes()
    return {
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def pack_groups(rows: list[dict]) -> list[tuple[int, list[dict]]]:
    """Group ordered months without allowing bucket or order drift."""
    months = [row.get("month") for row in rows]
    if months != sorted(set(months)):
        raise ValueError("Point pack months are not ordered")
    groups: list[tuple[int, list[dict]]] = []
    for row in rows:
        key = pack_key(row["month"])
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(row)
    return groups


def write_packs(root: Path, rows: list[dict]) -> list[dict]:
    """Publish deterministic point packs while retaining monthly assets."""
    root.mkdir(parents=True, exist_ok=True)
    packs = []
    keep = set()
    for key, group in pack_groups(rows):
        name = pack_path(key)
        keep.add(name)
        path = root / name
        atomic_write_bytes(path, pack_bytes(root, group))
        packs.append(
            {
                "months": [row["month"] for row in group],
                "count": sum(row["count"] for row in group),
                "counts": {
                    scope: sum(row["counts"][scope] for row in group)
                    for scope in SCOPES
                },
                "points": asset_meta(path),
            }
        )
    for path in root.glob("p*.bin"):
        if PACK_PATH.fullmatch(path.name) and path.name not in keep:
            path.unlink()
    return packs


def sync_packs(root: Path, rows: list[dict], expected: list[dict]) -> None:
    """Publish packs and require deterministic agreement with a staged set."""
    if write_packs(root, rows) != expected:
        raise ValueError("Cloud join point packs drifted")


def check_bytes(content: bytes, count: int, counts: dict) -> None:
    """Validate one pack's physical point contract."""
    try:
        magic, saved = struct.unpack("<8sI", content[:12])
        points = np.frombuffer(content[12 : 12 + count * 12], dtype="<f4")
        scopes = np.frombuffer(content[12 + count * 12 :], dtype=np.uint8)
        expected = np.asarray([counts[scope] for scope in SCOPES])
        actual = np.bincount(scopes, minlength=len(SCOPES))
    except (KeyError, TypeError, ValueError, struct.error) as error:
        raise RuntimeError("Point pack contract drifted") from error
    if (
        magic != PACK_MAGIC
        or saved != count
        or len(content) != 12 + count * 13
        or points.size != count * 3
        or not np.isfinite(points).all()
        or np.any(scopes >= len(SCOPES))
        or not np.array_equal(actual, expected)
    ):
        raise RuntimeError("Point pack contract drifted")


def check_packs(root: Path, rows: list[dict], packs: object) -> None:
    """Reconcile every pack with its retained monthly source bytes."""
    if not isinstance(packs, list) or not packs:
        raise RuntimeError("Point pack manifest is invalid")
    groups = pack_groups(rows)
    if len(packs) != len(groups):
        raise RuntimeError("Point pack manifest is incomplete")
    flattened = []
    paths = []
    for pack, (key, group) in zip(packs, groups, strict=True):
        months = [row["month"] for row in group]
        count = sum(row["count"] for row in group)
        counts = {scope: sum(row["counts"][scope] for row in group) for scope in SCOPES}
        if not isinstance(pack, dict):
            raise RuntimeError("Point pack manifest is invalid")
        meta = pack.get("points")
        path = root / meta.get("path", "") if isinstance(meta, dict) else root
        if (
            pack.get("months") != months
            or pack.get("count") != count
            or pack.get("counts") != counts
            or not valid_asset(path, meta)
            or path.name != pack_path(key)
            or meta.get("bytes") != 12 + count * 13
        ):
            raise RuntimeError("Point pack manifest drifted")
        content = path.read_bytes()
        check_bytes(content, count, counts)
        if content != pack_bytes(root, group):
            raise RuntimeError("Point pack rows drifted")
        flattened.extend(months)
        paths.append(path.name)
    if flattened != [row["month"] for row in rows] or paths != sorted(set(paths)):
        raise RuntimeError("Point pack coverage drifted")


def packs_ready(root: Path, rows: list[dict], cloud: dict) -> bool:
    """Return whether one prior cloud has complete reusable point packs."""
    if cloud.get("point_pack") != PACK_MODE or cloud.get("pack_months") != PACK_MONTHS:
        return False
    try:
        check_packs(root, rows, cloud.get("packs"))
    except RuntimeError:
        return False
    return True


def pack_changes(
    root: Path, rows: list[dict], cloud: dict, changed: list[dict]
) -> list[dict]:
    """Force one cheap worker when a legacy cloud needs pack migration."""
    if changed or not rows or packs_ready(root, cloud.get("shards", []), cloud):
        return changed
    return [rows[-1]]
