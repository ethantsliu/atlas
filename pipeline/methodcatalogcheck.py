"""Verification for the bounded evidence-free browser method catalog tier."""

from __future__ import annotations

from collections import Counter
from typing import Callable

from methods import candidate_id
from methodcatalog import IDENTITY_COLUMNS, identity_row
from methodtree import (
    Limits,
    compact_row,
    id_digest,
    row_key,
    search_words,
    summary_value,
)


def _node_key(node: dict) -> tuple:
    """Return the canonical order for one search route descriptor."""
    return (
        node["prefix"],
        node.get("hash_prefix", ""),
        node.get("route_mode", ""),
        node["path"],
    )


def _identity_check(row: dict, minimum: int) -> None:
    compact = compact_row(row)
    if (
        candidate_id(row["label"]) != row["id"]
        or row["support_count"] < minimum
        or row["mention_count"] < row["support_count"]
        or sum(row["scope_counts"].values()) != row["support_count"]
        or row["first_year"] > row["last_year"]
        or identity_row(compact | {"evidence": []}, row["ordinal"])["full_row_sha256"]
        == row["full_row_sha256"]
    ):
        # The final inequality prevents accepting a digest of the compact surrogate.
        raise ValueError("Catalog identity invariants or full-row binding are invalid")


def _read_node(
    root,
    descriptor: dict,
    route: str,
    limits: Limits,
    seen: set[str],
    read_asset: Callable,
) -> dict:
    leaf = descriptor["kind"] == "leaf"
    stem = ("search" if route == "search" else "detail") if leaf else f"{route}-route"
    raw = (
        limits.search_raw
        if route == "search" and leaf
        else limits.detail_raw
        if leaf
        else limits.router_raw
    )
    zipped = (
        limits.search_gzip
        if route == "search" and leaf
        else limits.detail_gzip
        if leaf
        else limits.router_gzip
    )
    return read_asset(root, descriptor, seen, stem, raw, zipped)[0]


def _search_binding(body: dict, descriptor: dict, corpus: str, full_sha: str) -> None:
    """Validate immutable body, descriptor, corpus, and release bindings."""
    if (
        body["corpus_manifest_sha256"] != corpus
        or body["full_asset_sha256"] != full_sha
        or body["prefix"] != descriptor["prefix"]
        or body.get("hash_prefix", "") != descriptor.get("hash_prefix", "")
    ):
        raise ValueError("Catalog search route binding disagrees")


def _search_children(body: dict) -> list[dict]:
    """Require ordered, unique, and strictly advancing search routes."""
    shards = body["shards"]
    if shards != sorted(shards, key=_node_key):
        raise ValueError("Catalog search children are not canonically ordered")
    keys = [(item["prefix"], item.get("hash_prefix", "")) for item in shards]
    if len(keys) != len(set(keys)):
        raise ValueError("Catalog search child routes overlap")
    for child in shards:
        if body["route_mode"] == "word":
            advances = child["prefix"].startswith(body["prefix"])
            terminal = child.get("route_mode") == "hash"
            valid = advances and (not terminal or child["prefix"] == body["prefix"])
        else:
            current = body.get("hash_prefix", "")
            child_hash = child.get("hash_prefix", "")
            valid = (
                child["prefix"] == body["prefix"]
                and child_hash.startswith(current)
                and len(child_hash) > len(current)
            )
        if not valid:
            raise ValueError("Catalog search route does not advance")
    return shards


def _walk_identities(
    root,
    descriptor: dict,
    corpus: str,
    full_sha: str,
    minimum: int,
    limits: Limits,
    seen: set[str],
    read_asset: Callable,
    identities: dict[int, dict],
    hops: int = 0,
) -> int:
    if hops > 32:
        raise ValueError("Catalog identity routing exceeds its depth cap")
    body = _read_node(root, descriptor, "detail", limits, seen, read_asset)
    common = (
        body["corpus_manifest_sha256"] == corpus
        and body["full_asset_sha256"] == full_sha
        and body["route_kind"] == "detail"
        and body["route_mode"] == "ordinal"
        and body["start_ordinal"] == descriptor["start_ordinal"]
        and body["end_ordinal"] == descriptor["end_ordinal"]
    )
    if not common or body.get("prefix") != descriptor["prefix"]:
        raise ValueError("Catalog identity route binding disagrees")
    if descriptor["kind"] == "leaf":
        if body["columns"] != list(IDENTITY_COLUMNS):
            raise ValueError("Catalog identity leaf columns disagree")
        rows = [
            dict(zip(IDENTITY_COLUMNS, values, strict=True)) for values in body["rows"]
        ]
        expected = list(range(body["start_ordinal"], body["end_ordinal"] + 1))
        if [row["ordinal"] for row in rows] != expected or len(rows) != descriptor[
            "row_count"
        ]:
            raise ValueError("Catalog identity leaf is not contiguous and ordered")
        for row in rows:
            _identity_check(row, minimum)
            if row["ordinal"] in identities:
                raise ValueError("Catalog identity is reachable more than once")
            identities[row["ordinal"]] = row
        return len(rows)
    shards = body["shards"]
    if not shards or shards != sorted(shards, key=lambda item: item["start_ordinal"]):
        raise ValueError("Catalog identity children are not ordered")
    cursor = body["start_ordinal"]
    count = 0
    for child in shards:
        if child["start_ordinal"] != cursor or child["end_ordinal"] < cursor:
            raise ValueError("Catalog identity child ranges overlap or have gaps")
        count += _walk_identities(
            root,
            child,
            corpus,
            full_sha,
            minimum,
            limits,
            seen,
            read_asset,
            identities,
            hops + 1,
        )
        cursor = child["end_ordinal"] + 1
    if (
        cursor - 1 != body["end_ordinal"]
        or count != body["row_count"]
        or count != descriptor["row_count"]
    ):
        raise ValueError("Catalog identity router counts or ranges disagree")
    return count


def _walk_search(
    root,
    descriptor: dict,
    corpus: str,
    full_sha: str,
    limits: Limits,
    seen: set[str],
    read_asset: Callable,
    identities: dict[int, dict],
    observed: Counter,
    hops: int = 0,
) -> int:
    if hops > 32:
        raise ValueError("Catalog search routing exceeds its depth cap")
    body = _read_node(root, descriptor, "search", limits, seen, read_asset)
    _search_binding(body, descriptor, corpus, full_sha)
    if descriptor["kind"] == "leaf":
        ordinals = body["ordinals"]
        if (
            ordinals != sorted(set(ordinals))
            or len(ordinals) != descriptor["row_count"]
        ):
            raise ValueError("Catalog search postings are duplicated or unordered")
        prefix = descriptor["prefix"]
        for ordinal in ordinals:
            row = identities.get(ordinal)
            if row is None:
                raise ValueError("Catalog search references an unknown ordinal")
            if descriptor.get("hash_prefix") and not id_digest(row).startswith(
                descriptor["hash_prefix"]
            ):
                raise ValueError("Catalog search posting is outside its hash route")
            words = [
                word for word in search_words(row["label"]) if word.startswith(prefix)
            ]
            if not words:
                raise ValueError("Catalog search posting is outside its word route")
            observed.update((ordinal, word) for word in words)
        return len(ordinals)
    if body["route_kind"] != "search" or body["route_mode"] != descriptor["route_mode"]:
        raise ValueError("Catalog search router role disagrees")
    shards = _search_children(body)
    count = 0
    for child in shards:
        count += _walk_search(
            root,
            child,
            corpus,
            full_sha,
            limits,
            seen,
            read_asset,
            identities,
            observed,
            hops + 1,
        )
    if count != body["row_count"] or count != descriptor["row_count"]:
        raise ValueError("Catalog search router counts disagree")
    return count


def _catalog_roots(index: dict, top: dict, search: dict, detail: dict) -> tuple:
    """Validate catalog root provenance, counts, notice, and route ordering."""
    full_sha = index["assets"]["download"]["sha256"]
    if any(body.get("full_asset_sha256") != full_sha for body in (top, search, detail)):
        raise ValueError("Catalog assets are not bound to the full release digest")
    qualified = index["coverage"]["qualified_candidates"]
    counts = (
        detail["start_ordinal"] == 0,
        detail["end_ordinal"] == qualified - 1,
        detail["row_count"] == qualified,
        index["assets"]["details"]["row_count"] == qualified,
        index["assets"]["download"]["row_count"] == qualified,
    )
    if not all(counts):
        raise ValueError("Catalog root identity range or counts disagree")
    sentence = (
        "Evidence spans are available only in the immutable full release download."
    )
    if sentence not in index["notice"]:
        raise ValueError("Catalog evidence availability notice is missing")
    details = detail["shards"]
    if details != sorted(details, key=lambda item: item["start_ordinal"]):
        raise ValueError("Catalog root identity routes are unordered")
    cursor = 0
    for child in details:
        if child["start_ordinal"] != cursor:
            raise ValueError("Catalog root identity routes have gaps or overlaps")
        cursor = child["end_ordinal"] + 1
    if cursor != qualified:
        raise ValueError("Catalog root identity routes are incomplete")
    searches = search["shards"]
    if searches != sorted(searches, key=_node_key):
        raise ValueError("Catalog root search routes are unordered")
    return qualified, full_sha, details, searches


def _catalog_results(
    index: dict,
    summary: dict,
    top: dict,
    search: dict,
    detail: dict,
    identities: dict[int, dict],
    observed: Counter,
    detail_count: int,
    search_count: int,
) -> None:
    """Reconcile exact identity/search coverage, top rows, and aggregates."""
    ordinals = list(range(index["coverage"]["qualified_candidates"]))
    if sorted(identities) != ordinals or detail_count != len(ordinals):
        raise ValueError("Catalog identity coverage is incomplete")
    expected = {
        (ordinal, word)
        for ordinal, row in identities.items()
        for word in search_words(row["label"])
    }
    if set(observed) != expected or any(value != 1 for value in observed.values()):
        raise ValueError("Catalog search routes are incomplete or duplicated")
    counts = (
        search_count == search["row_count"],
        detail_count == detail["row_count"],
        index["assets"]["search"]["row_count"] == search_count,
    )
    if not all(counts):
        raise ValueError("Catalog root route counts disagree")
    ordered = [identities[ordinal] for ordinal in ordinals]
    top_valid = top["rows"] == ordered[:200]
    count_valid = index["assets"]["top"]["row_count"] == len(top["rows"])
    if not top_valid or not count_valid:
        raise ValueError("Catalog top rows are not the canonical identity prefix")
    compacts = [compact_row(row) for row in ordered]
    if compacts != sorted(compacts, key=row_key):
        raise ValueError("Catalog identities are not canonically ordered")
    if summary != summary_value(index, compacts):
        raise ValueError("Catalog summary aggregates do not reconcile")


def verify_catalog(
    root,
    index: dict,
    summary: dict,
    top: dict,
    search: dict,
    detail: dict,
    limits: Limits,
    seen: set[str],
    read_asset: Callable,
) -> None:
    """Prove catalog provenance, exact identity coverage, and discoverability."""
    corpus = index["corpus"]["manifest_sha256"]
    minimum = index["extraction"]["minimum_support"]
    _, full_sha, detail_shards, search_shards = _catalog_roots(
        index, top, search, detail
    )
    identities: dict[int, dict] = {}
    detail_count = sum(
        _walk_identities(
            root, child, corpus, full_sha, minimum, limits, seen, read_asset, identities
        )
        for child in detail_shards
    )
    observed: Counter = Counter()
    search_count = sum(
        _walk_search(
            root,
            child,
            corpus,
            full_sha,
            limits,
            seen,
            read_asset,
            identities,
            observed,
        )
        for child in search_shards
    )
    _catalog_results(
        index,
        summary,
        top,
        search,
        detail,
        identities,
        observed,
        detail_count,
        search_count,
    )
