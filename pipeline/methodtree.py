"""Deterministic, bounded JSON routing trees for browser method assets."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from files import atomic_write_bytes


GENERATOR = "methods-browser-1"
STATUS = "corpus-extracted-candidates"
NORMALIZATION = "nfkc-lower-alnum-space-1"
MIN_QUERY = 3
SEARCH_RAW = 256 * 1024
SEARCH_GZIP = 64 * 1024
DETAIL_RAW = 128 * 1024
DETAIL_GZIP = 32 * 1024
ROUTER_RAW = 64 * 1024
ROUTER_GZIP = 16 * 1024
MAX_SEARCH_PREFIX = 12
MAX_HASH_PREFIX = 8
HEX = re.compile(r"^[0-9a-f]{64}$")
MAX_PACKAGE_BYTES = 100 * 1024 * 1024


class PackageTooLarge(ValueError):
    """Signal that a browser tier crossed its hard same-origin byte budget."""


@dataclass(frozen=True)
class Limits:
    """Raw and deterministic-gzip byte ceilings for generated JSON."""

    search_raw: int = SEARCH_RAW
    search_gzip: int = SEARCH_GZIP
    detail_raw: int = DETAIL_RAW
    detail_gzip: int = DETAIL_GZIP
    router_raw: int = ROUTER_RAW
    router_gzip: int = ROUTER_GZIP


def json_bytes(value: object) -> bytes:
    """Encode canonical, browser-readable JSON with one trailing newline."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def gzip_length(content: bytes) -> int:
    """Measure a stable gzip representation for the transfer-size budget."""
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as stream:
        stream.write(content)
    return len(output.getvalue())


def fits(content: bytes, raw: int, compressed: int) -> bool:
    """Return whether both browser transfer ceilings are satisfied."""
    return len(content) <= raw and gzip_length(content) <= compressed


def compact_row(row: dict) -> dict:
    """Strip evidence while retaining the complete search/result summary."""
    keys = (
        "id",
        "status",
        "label",
        "kind",
        "head",
        "support_count",
        "mention_count",
        "first_year",
        "last_year",
        "scope_counts",
    )
    return {key: row[key] for key in keys}


def row_key(row: dict) -> tuple:
    """Return the canonical extraction ranking with an identity tie-breaker."""
    return (-row["support_count"], row["label"], row["head"], row["id"])


def search_words(label: str) -> tuple[str, ...]:
    """Normalize every searchable label word with the public browser policy."""
    normalized = unicodedata.normalize("NFKC", label).lower()
    normalized = "".join(
        char if char.isascii() and char.isalnum() else " " for char in normalized
    )
    return tuple(
        sorted({word for word in normalized.split() if len(word) >= MIN_QUERY})
    )


def support_bins(rows: list[dict], minimum: int) -> list[dict]:
    """Build deterministic, exhaustive support-frequency histogram bins."""
    edges = [minimum, *(edge for edge in (10, 100, 1000, 10000) if edge > minimum)]
    result = []
    for index, lower in enumerate(edges):
        upper = edges[index + 1] - 1 if index + 1 < len(edges) else None
        result.append(
            {
                "minimum": lower,
                "maximum": upper,
                "count": sum(
                    1
                    for row in rows
                    if row["support_count"] >= lower
                    and (upper is None or row["support_count"] <= upper)
                ),
            }
        )
    return result


def summary_value(source: dict, rows: list[dict]) -> dict:
    """Aggregate exact small statistics without changing candidate semantics."""
    kinds = Counter(row["kind"] for row in rows)
    scopes = Counter()
    years = Counter(row["first_year"] for row in rows)
    for row in rows:
        scopes.update(row["scope_counts"])
    return {
        "schema_version": 1,
        "corpus_manifest_sha256": source["corpus"]["manifest_sha256"],
        "qualified_candidates": len(rows),
        "distinct_extracted_candidates": source["coverage"][
            "distinct_extracted_candidates"
        ],
        "curated_families": source["curated_families"],
        "by_kind": [
            {"kind": kind, "count": kinds[kind]}
            for kind in ("method-noun", "process-technique")
        ],
        "by_scope": [
            {"scope": scope, "count": scopes[scope]}
            for scope in ("likely", "possible", "outside")
        ],
        "by_support": support_bins(rows, source["extraction"]["minimum_support"]),
        "by_first_year": [
            {"year": year, "count": years[year]} for year in sorted(years)
        ],
    }


def id_digest(row: dict) -> str:
    """Return the validated hexadecimal portion of a method candidate ID."""
    prefix, separator, digest = row["id"].partition(":")
    if prefix != "method-candidate" or separator != ":" or not HEX.fullmatch(digest):
        raise ValueError("Method candidate ID cannot be routed")
    return digest


class Store:
    """Write content-addressed children and return strict public descriptors."""

    def __init__(self, root: Path, max_bytes: int = MAX_PACKAGE_BYTES):
        self.root = root
        self.paths: set[str] = set()
        self.max_bytes = max_bytes
        self.total_bytes = 0

    def write(self, stem: str, value: dict, rows: int) -> dict:
        content = json_bytes(value)
        digest = hashlib.sha256(content).hexdigest()
        name = f"{stem}-{digest[:16]}.json"
        if name in self.paths:
            existing = self.root / name
            if not existing.is_file() or existing.read_bytes() != content:
                raise ValueError("Method asset address collision")
        else:
            if self.total_bytes + len(content) > self.max_bytes:
                raise PackageTooLarge(
                    "Method browser package exceeds the 100 MiB Pages boundary"
                )
            atomic_write_bytes(self.root / name, content)
            self.paths.add(name)
            self.total_bytes += len(content)
        return {
            "path": name,
            "encoding": "json",
            "sha256": digest,
            "bytes": len(content),
            "row_count": rows,
        }


def node_desc(descriptor: dict, kind: str, prefix: str, **extra: str) -> dict:
    """Add deterministic routing metadata to one content descriptor."""
    return {"kind": kind, "prefix": prefix, **extra, **descriptor}


def search_leaf(
    store: Store,
    corpus: str,
    prefix: str,
    postings: list[tuple[dict, str]],
    limits: Limits,
    hash_prefix: str = "",
) -> dict | None:
    """Write one deduplicated compact search leaf when it fits both caps."""
    unique = {row["id"]: row for row, _ in postings}
    rows = [compact_row(row) for row in sorted(unique.values(), key=row_key)]
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "prefix": prefix,
        "hash_prefix": hash_prefix,
        "rows": rows,
    }
    content = json_bytes(body)
    if not fits(content, limits.search_raw, limits.search_gzip):
        return None
    stem = f"search-{prefix[:MAX_SEARCH_PREFIX]}"
    descriptor = store.write(stem, body, len(rows))
    extra = {"hash_prefix": hash_prefix} if hash_prefix else {}
    return node_desc(descriptor, "leaf", prefix, **extra)


def search_hash(
    store: Store,
    corpus: str,
    prefix: str,
    postings: list[tuple[dict, str]],
    limits: Limits,
    hash_prefix: str = "",
) -> dict:
    """Split an overfull terminal word bucket by candidate identity hash."""
    leaf = search_leaf(store, corpus, prefix, postings, limits, hash_prefix)
    if leaf is not None:
        if not hash_prefix:
            leaf["route_mode"] = "hash"
        return leaf
    if len(hash_prefix) >= MAX_HASH_PREFIX:
        raise ValueError("Search leaf exceeds its cap at maximum hash depth")
    groups: dict[str, list[tuple[dict, str]]] = {}
    for posting in postings:
        digest = id_digest(posting[0])
        child = digest[: len(hash_prefix) + 1]
        groups.setdefault(child, []).append(posting)
    shards = [
        search_hash(store, corpus, prefix, groups[key], limits, key)
        for key in sorted(groups)
    ]
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "route_kind": "search",
        "route_mode": "hash",
        "prefix": prefix,
        "hash_prefix": hash_prefix,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    content = json_bytes(body)
    if not fits(content, limits.router_raw, limits.router_gzip):
        raise ValueError("Search hash router exceeds its cap")
    descriptor = store.write("search-route", body, body["row_count"])
    return node_desc(
        descriptor,
        "router",
        prefix,
        route_mode="hash",
        hash_prefix=hash_prefix,
    )


def search_node(
    store: Store,
    corpus: str,
    prefix: str,
    postings: list[tuple[dict, str]],
    limits: Limits,
) -> dict:
    """Build the bounded adaptive word-prefix tree for one posting bucket."""
    if len(prefix) >= MIN_QUERY:
        leaf = search_leaf(store, corpus, prefix, postings, limits)
        if leaf is not None:
            return leaf
    if len(prefix) >= MAX_SEARCH_PREFIX:
        return search_hash(store, corpus, prefix, postings, limits)
    exact: list[tuple[dict, str]] = []
    groups: dict[str, list[tuple[dict, str]]] = {}
    for posting in postings:
        word = posting[1]
        if len(word) == len(prefix):
            exact.append(posting)
        else:
            child = word[: len(prefix) + 1]
            groups.setdefault(child, []).append(posting)
    shards = []
    if exact:
        shards.append(search_hash(store, corpus, prefix, exact, limits))
    shards.extend(
        search_node(store, corpus, key, groups[key], limits) for key in sorted(groups)
    )
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "route_kind": "search",
        "route_mode": "word",
        "prefix": prefix,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    content = json_bytes(body)
    if not fits(content, limits.router_raw, limits.router_gzip):
        raise ValueError("Search word router exceeds its cap")
    descriptor = store.write("search-route", body, body["row_count"])
    return node_desc(descriptor, "router", prefix, route_mode="word")


def build_search(store: Store, corpus: str, rows: list[dict], limits: Limits) -> dict:
    """Build the lazily loaded search manifest and all adaptive children."""
    postings = [(row, word) for row in rows for word in search_words(row["label"])]
    if any(not search_words(row["label"]) for row in rows):
        raise ValueError("Every method candidate must have a searchable word")
    groups: dict[str, list[tuple[dict, str]]] = {}
    for posting in postings:
        groups.setdefault(posting[1][:MIN_QUERY], []).append(posting)
    shards = [
        search_node(store, corpus, prefix, groups[prefix], limits)
        for prefix in sorted(groups)
    ]
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "normalization": NORMALIZATION,
        "minimum_query_length": MIN_QUERY,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    content = json_bytes(body)
    if not fits(content, limits.router_raw, limits.router_gzip):
        shards = route_roots(store, corpus, "search", shards, limits)
        body["shards"] = shards
        content = json_bytes(body)
        if not fits(content, limits.router_raw, limits.router_gzip):
            raise ValueError("Search routing manifest exceeds its cap")
    return store.write("search", body, body["row_count"])


def detail_leaf(
    store: Store,
    corpus: str,
    prefix: str,
    rows: list[dict],
    limits: Limits,
) -> dict | None:
    """Write one full candidate leaf when both detail ceilings permit it."""
    ordered = sorted(rows, key=row_key)
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "prefix": prefix,
        "rows": ordered,
    }
    content = json_bytes(body)
    if not fits(content, limits.detail_raw, limits.detail_gzip):
        return None
    descriptor = store.write(f"detail-{prefix}", body, len(ordered))
    return node_desc(descriptor, "leaf", prefix)


def detail_node(
    store: Store,
    corpus: str,
    prefix: str,
    rows: list[dict],
    limits: Limits,
) -> dict:
    """Build one adaptive leading-ID-hash detail subtree."""
    if len(prefix) >= 2:
        leaf = detail_leaf(store, corpus, prefix, rows, limits)
        if leaf is not None:
            return leaf
    if len(prefix) >= MAX_HASH_PREFIX:
        raise ValueError("Detail leaf exceeds its cap at maximum hash depth")
    groups: dict[str, list[dict]] = {}
    for row in rows:
        child = id_digest(row)[: len(prefix) + 1]
        groups.setdefault(child, []).append(row)
    shards = [
        detail_node(store, corpus, key, groups[key], limits) for key in sorted(groups)
    ]
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "route_kind": "detail",
        "route_mode": "hash",
        "prefix": prefix,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    content = json_bytes(body)
    if not fits(content, limits.router_raw, limits.router_gzip):
        raise ValueError("Detail hash router exceeds its cap")
    descriptor = store.write("detail-route", body, body["row_count"])
    return node_desc(descriptor, "router", prefix, route_mode="hash")


def build_details(store: Store, corpus: str, rows: list[dict], limits: Limits) -> dict:
    """Build the lazy detail manifest and full evidence-bearing leaves."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(id_digest(row)[:2], []).append(row)
    shards = [
        detail_node(store, corpus, prefix, groups[prefix], limits)
        for prefix in sorted(groups)
    ]
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "prefix_bits": 8,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    content = json_bytes(body)
    if not fits(content, limits.router_raw, limits.router_gzip):
        shards = route_roots(store, corpus, "detail", shards, limits)
        body["shards"] = shards
        content = json_bytes(body)
        if not fits(content, limits.router_raw, limits.router_gzip):
            raise ValueError("Detail routing manifest exceeds its cap")
    return store.write("details", body, body["row_count"])


def route_body(
    store: Store,
    corpus: str,
    route_kind: str,
    prefix: str,
    shards: list[dict],
    limits: Limits,
) -> dict:
    """Write a compact hierarchy node, recursively grouping if necessary."""
    mode = "word" if route_kind == "search" else "hash"
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "route_kind": route_kind,
        "route_mode": mode,
        "prefix": prefix,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    content = json_bytes(body)
    if not fits(content, limits.router_raw, limits.router_gzip):
        shards = route_roots(store, corpus, route_kind, shards, limits, len(prefix))
        body["shards"] = shards
        content = json_bytes(body)
        if not fits(content, limits.router_raw, limits.router_gzip):
            raise ValueError("Method hierarchy router exceeds its cap")
    stem = "search-route" if route_kind == "search" else "detail-route"
    descriptor = store.write(stem, body, body["row_count"])
    return node_desc(descriptor, "router", prefix, route_mode=mode)


def route_roots(
    store: Store,
    corpus: str,
    route_kind: str,
    shards: list[dict],
    limits: Limits,
    depth: int = 0,
) -> list[dict]:
    """Collapse a wide flat route list into bounded deterministic radix nodes."""
    groups: dict[str, list[dict]] = {}
    for shard in shards:
        prefix = shard["prefix"]
        if len(prefix) <= depth:
            raise ValueError("Method route cannot be hierarchically partitioned")
        groups.setdefault(prefix[: depth + 1], []).append(shard)
    result = []
    for prefix in sorted(groups):
        children = groups[prefix]
        if len(children) == 1:
            result.append(children[0])
        else:
            result.append(
                route_body(store, corpus, route_kind, prefix, children, limits)
            )
    return result
