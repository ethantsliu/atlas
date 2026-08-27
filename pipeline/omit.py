"""Bind historical cloud exclusions to reviewed public arXiv papers."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from node import clip_words


SCOPES = ("likely", "possible", "outside")


def archive_text(paper: dict) -> str:
    """Represent a paper with title, abstract, and categories—not title alone."""
    categories = ", ".join(paper.get("categories", []))
    return " ".join(
        part
        for part in (
            f"research paper: {clip_words(paper.get('title'), 160)}",
            f"abstract: {clip_words(paper.get('abstract'), 360)}",
            f"areas: {clip_words(categories, 80)}",
        )
        if part.split(": ", 1)[-1]
    )


def ids_hash(identifiers: list[str] | set[str]) -> str:
    """Hash one sorted set of canonical public arXiv identifiers."""
    body = json.dumps(sorted(identifiers), separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def load_foreground(path: Path) -> dict[str, set[str]]:
    """Load reviewed arXiv IDs from the content-addressed public paper bundle."""
    try:
        core = json.loads(path.read_text(encoding="utf-8"))
        asset = core["paper_asset"]
        relative = asset["path"].removeprefix("/")
        bundle_path = path.parents[1] / relative
        content = bundle_path.read_bytes()
        bundle = json.loads(content)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        AttributeError,
    ) as error:
        raise RuntimeError("Foreground paper bundle is invalid") from error
    if (
        asset.get("sha256") != hashlib.sha256(content).hexdigest()
        or asset.get("bytes") != len(content)
        or asset.get("paper_count") != len(bundle.get("papers", []))
        or bundle.get("schema_version") != 1
    ):
        raise RuntimeError("Foreground paper bundle is invalid")
    months: dict[str, set[str]] = {}
    for paper in bundle["papers"]:
        if not isinstance(paper, dict) or paper.get("record_kind") != "paper":
            continue
        stable = paper.get("stable_id")
        published = paper.get("published")
        if not isinstance(stable, str) or not stable.startswith("arxiv:"):
            continue
        if not isinstance(published, str) or len(published) < 7:
            raise RuntimeError("Foreground arXiv paper has no publication month")
        month = published[:7]
        try:
            int(month[:4])
            month_number = int(month[5:])
        except ValueError as error:
            raise RuntimeError("Foreground arXiv paper month is invalid") from error
        if len(month) != 7 or month[4] != "-" or not 1 <= month_number <= 12:
            raise RuntimeError("Foreground arXiv paper month is invalid")
        identifier = stable.removeprefix("arxiv:")
        tail = identifier.rsplit("v", 1)[-1]
        identifier = identifier.rsplit("v", 1)[0] if tail.isdigit() else identifier
        if not identifier or any(character.isspace() for character in identifier):
            raise RuntimeError("Foreground arXiv paper ID is invalid")
        months.setdefault(month, set()).add(identifier)
    return months


def foreground_hash(foreground: dict[str, set[str]]) -> str:
    """Hash the complete month-routed foreground exclusion policy."""
    rows = [
        f"{month}:{identifier}"
        for month in sorted(foreground)
        for identifier in sorted(foreground[month])
    ]
    return ids_hash(rows)


def cloud_manifest(
    rows: list[dict],
    foreground: dict[str, set[str]],
    model: str,
    model_digest: str,
    model_revision: str,
    anchor_sha256: str,
    anchors: dict,
    anchor_count: int,
    neighbor_count: int,
) -> dict:
    """Assemble one count-reconciled physical-dedupe cloud manifest."""
    omitted_ids = [identifier for row in rows for identifier in row["omitted_ids"]]
    return {
        "schema_version": 1,
        "source": "arxiv",
        "model": model,
        "model_digest": model_digest,
        "model_revision": model_revision,
        "projection": "anchor-cosine-8-v1",
        "point_bytes": 13,
        "relation": "anchor-cosine-top8-v1",
        "route_bytes": 4,
        "neighbor_count": neighbor_count,
        "anchor_count": anchor_count,
        "anchor_sha256": anchor_sha256,
        "anchors": anchors,
        "source_count": sum(row["source_count"] for row in rows),
        "count": sum(row["count"] for row in rows),
        "counts": {
            scope: sum(row["counts"][scope] for row in rows) for scope in SCOPES
        },
        "omitted_count": len(omitted_ids),
        "omitted_counts": {
            scope: sum(row["omitted_counts"][scope] for row in rows) for scope in SCOPES
        },
        "omitted_sha256": ids_hash(omitted_ids),
        "foreground_sha256": foreground_hash(foreground),
        "shards": rows,
    }


def cloud_cover(papers: list[dict], candidates: set[str]) -> tuple[list[dict], dict]:
    """Split exact foreground overlaps from one exhaustive source month."""
    omitted = [paper for paper in papers if paper["id"] in candidates]
    kept = [paper for paper in papers if paper["id"] not in candidates]
    omitted_ids = [paper["id"] for paper in omitted]
    return kept, {
        "source_count": len(papers),
        "source_counts": {
            scope: sum(paper["scope"] == scope for paper in papers) for scope in SCOPES
        },
        "foreground_sha256": ids_hash(candidates),
        "omitted_count": len(omitted),
        "omitted_counts": {
            scope: sum(paper["scope"] == scope for paper in omitted) for scope in SCOPES
        },
        "omitted_ids": omitted_ids,
        "omitted_sha256": ids_hash(omitted_ids),
    }


def reuse_bytes(
    root: Path,
    row: dict,
    identifiers: list[str],
    magic: bytes,
    source_sha: str | None,
    route_magic: bytes,
    route_width: int,
    anchor_sha256: str,
) -> tuple[bytes, bytes] | None:
    """Filter aligned prior point and route buffers by paper identity."""
    if (source_sha is not None and row.get("source_sha256") != source_sha) or row.get(
        "anchor_sha256"
    ) != anchor_sha256:
        return None
    try:
        meta = json.loads((root / row["meta"]["path"]).read_text(encoding="utf-8"))
        content = (root / row["points"]["path"]).read_bytes()
        routes = (root / row["routes"]["path"]).read_bytes()
        prior_ids = [paper[0] for paper in meta["papers"]]
        saved_magic, count = struct.unpack("<8sI", content[:12])
        route_head = struct.unpack("<8sIHH32s32s", routes[:80])
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        struct.error,
    ):
        return None
    route_saved, route_count, neighbors, _anchors, _rows, anchor_digest = route_head
    if (
        saved_magic != magic
        or route_saved != route_magic
        or count != len(prior_ids)
        or route_count != count
        or neighbors < 1
        or route_width != neighbors * 4
        or len(content) != 12 + 13 * count
        or len(routes) != 80 + route_width * count
        or anchor_digest.hex() != anchor_sha256
        or len(set(prior_ids)) != count
    ):
        return None
    indexes = {identifier: index for index, identifier in enumerate(prior_ids)}
    if any(identifier not in indexes for identifier in identifiers):
        return None
    positions = b"".join(
        content[12 + indexes[identifier] * 12 : 24 + indexes[identifier] * 12]
        for identifier in identifiers
    )
    scope_start = 12 + count * 12
    scopes = bytes(
        content[scope_start + indexes[identifier]] for identifier in identifiers
    )
    route_rows = b"".join(
        routes[
            80 + indexes[identifier] * route_width : 80
            + (indexes[identifier] + 1) * route_width
        ]
        for identifier in identifiers
    )
    row_digest = hashlib.sha256(
        json.dumps(identifiers, separators=(",", ":")).encode()
    ).digest()
    route_header = struct.pack(
        "<8sIHH32s32s",
        route_magic,
        len(identifiers),
        neighbors,
        route_head[3],
        row_digest,
        bytes.fromhex(anchor_sha256),
    )
    points = struct.pack("<8sI", magic, len(identifiers)) + positions + scopes
    return points, route_header + route_rows


def read_cloud(path: Path) -> dict:
    """Read the prior incremental point manifest when present."""
    if not path.exists():
        return {"schema_version": 1, "shards": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Archive point manifest is invalid") from error
    if value.get("schema_version") != 1 or not isinstance(value.get("shards"), list):
        raise RuntimeError("Archive point manifest has an invalid contract")
    return value
