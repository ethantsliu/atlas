"""Compact, evidence-free method catalog routing for bounded browser releases."""

from __future__ import annotations

import hashlib

from methodtree import (
    MAX_HASH_PREFIX,
    MAX_SEARCH_PREFIX,
    MIN_QUERY,
    NORMALIZATION,
    Limits,
    Store,
    fits,
    id_digest,
    json_bytes,
    node_desc,
    search_words,
)


IDENTITY_COLUMNS = (
    "ordinal",
    "full_row_sha256",
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


def full_row_sha256(row: dict) -> str:
    """Bind an evidence-free identity to its canonical full candidate object."""
    return hashlib.sha256(json_bytes(row).rstrip(b"\n")).hexdigest()


def identity_row(row: dict, ordinal: int) -> dict:
    """Return one unique compact identity with immutable full-row provenance."""
    return {
        "ordinal": ordinal,
        "full_row_sha256": full_row_sha256(row),
        **{
            key: row[key]
            for key in (
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
        },
    }


def identity_values(row: dict) -> list:
    """Encode one identity positionally under the immutable column contract."""
    return [row[key] for key in IDENTITY_COLUMNS]


def _search_leaf(
    store: Store,
    corpus: str,
    full_sha: str,
    prefix: str,
    postings: list[tuple[dict, str, int]],
    limits: Limits,
    hash_prefix: str = "",
) -> dict | None:
    ordinals = sorted({ordinal for _, _, ordinal in postings})
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "full_asset_sha256": full_sha,
        "prefix": prefix,
        "hash_prefix": hash_prefix,
        "ordinals": ordinals,
    }
    if not fits(json_bytes(body), limits.search_raw, limits.search_gzip):
        return None
    descriptor = store.write(
        f"search-{prefix[:MAX_SEARCH_PREFIX]}", body, len(ordinals)
    )
    extra = {"hash_prefix": hash_prefix} if hash_prefix else {}
    return node_desc(descriptor, "leaf", prefix, **extra)


def _search_hash(
    store: Store,
    corpus: str,
    full_sha: str,
    prefix: str,
    postings: list[tuple[dict, str, int]],
    limits: Limits,
    hash_prefix: str = "",
) -> dict:
    leaf = _search_leaf(store, corpus, full_sha, prefix, postings, limits, hash_prefix)
    if leaf is not None:
        if not hash_prefix:
            leaf["route_mode"] = "hash"
        return leaf
    if len(hash_prefix) >= MAX_HASH_PREFIX:
        raise ValueError("Catalog search leaf exceeds maximum hash depth")
    groups: dict[str, list[tuple[dict, str, int]]] = {}
    for posting in postings:
        child = id_digest(posting[0])[: len(hash_prefix) + 1]
        groups.setdefault(child, []).append(posting)
    shards = [
        _search_hash(store, corpus, full_sha, prefix, groups[key], limits, key)
        for key in sorted(groups)
    ]
    body = _search_router(corpus, full_sha, "hash", prefix, shards, hash_prefix)
    if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
        raise ValueError("Catalog search hash router exceeds its cap")
    descriptor = store.write("search-route", body, body["row_count"])
    return node_desc(
        descriptor, "router", prefix, route_mode="hash", hash_prefix=hash_prefix
    )


def _search_router(
    corpus: str,
    full_sha: str,
    mode: str,
    prefix: str,
    shards: list[dict],
    hash_prefix: str = "",
) -> dict:
    value = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "full_asset_sha256": full_sha,
        "route_kind": "search",
        "route_mode": mode,
        "prefix": prefix,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    if hash_prefix:
        value["hash_prefix"] = hash_prefix
    return value


def _search_node(
    store: Store,
    corpus: str,
    full_sha: str,
    prefix: str,
    postings: list[tuple[dict, str, int]],
    limits: Limits,
) -> dict:
    if len(prefix) >= MIN_QUERY:
        leaf = _search_leaf(store, corpus, full_sha, prefix, postings, limits)
        if leaf is not None:
            return leaf
    if len(prefix) >= MAX_SEARCH_PREFIX:
        return _search_hash(store, corpus, full_sha, prefix, postings, limits)
    exact: list[tuple[dict, str, int]] = []
    groups: dict[str, list[tuple[dict, str, int]]] = {}
    for posting in postings:
        word = posting[1]
        if len(word) == len(prefix):
            exact.append(posting)
        else:
            groups.setdefault(word[: len(prefix) + 1], []).append(posting)
    shards = []
    if exact:
        shards.append(_search_hash(store, corpus, full_sha, prefix, exact, limits))
    shards.extend(
        _search_node(store, corpus, full_sha, key, groups[key], limits)
        for key in sorted(groups)
    )
    body = _search_router(corpus, full_sha, "word", prefix, shards)
    if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
        raise ValueError("Catalog search word router exceeds its cap")
    descriptor = store.write("search-route", body, body["row_count"])
    return node_desc(descriptor, "router", prefix, route_mode="word")


def build_catalog_search(
    store: Store, corpus: str, full_sha: str, rows: list[dict], limits: Limits
) -> dict:
    """Build postings-only word routes; compact identities are never duplicated."""
    postings = [
        (row, word, ordinal)
        for ordinal, row in enumerate(rows)
        for word in search_words(row["label"])
    ]
    if any(not search_words(row["label"]) for row in rows):
        raise ValueError("Every method candidate must have a searchable word")
    groups: dict[str, list[tuple[dict, str, int]]] = {}
    for posting in postings:
        groups.setdefault(posting[1][:MIN_QUERY], []).append(posting)
    shards = [
        _search_node(store, corpus, full_sha, prefix, groups[prefix], limits)
        for prefix in sorted(groups)
    ]
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "full_asset_sha256": full_sha,
        "normalization": NORMALIZATION,
        "minimum_query_length": MIN_QUERY,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
        shards = _group_search_roots(store, corpus, full_sha, shards, limits, depth=0)
        body["shards"] = shards
        body["row_count"] = sum(item["row_count"] for item in shards)
        if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
            raise ValueError("Catalog search root exceeds its cap")
    return store.write("search", body, body["row_count"])


def _group_search_roots(
    store: Store,
    corpus: str,
    full_sha: str,
    shards: list[dict],
    limits: Limits,
    depth: int,
) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for shard in shards:
        prefix = shard["prefix"]
        if len(prefix) <= depth:
            raise ValueError("Catalog search route cannot be partitioned")
        groups.setdefault(prefix[: depth + 1], []).append(shard)
    result = []
    for prefix in sorted(groups):
        children = groups[prefix]
        if len(children) == 1:
            result.append(children[0])
            continue
        body = _search_router(corpus, full_sha, "word", prefix, children)
        if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
            children = _group_search_roots(
                store, corpus, full_sha, children, limits, depth + 1
            )
            body = _search_router(corpus, full_sha, "word", prefix, children)
        if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
            raise ValueError("Catalog search hierarchy router exceeds its cap")
        descriptor = store.write("search-route", body, body["row_count"])
        result.append(node_desc(descriptor, "router", prefix, route_mode="word"))
    return result


def _identity_leaf(
    store: Store,
    corpus: str,
    full_sha: str,
    rows: list[dict],
    limits: Limits,
) -> dict | None:
    start = rows[0]["ordinal"]
    end = rows[-1]["ordinal"]
    prefix = f"{start:08x}"
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "full_asset_sha256": full_sha,
        "route_kind": "detail",
        "route_mode": "ordinal",
        "prefix": prefix,
        "start_ordinal": start,
        "end_ordinal": end,
        "columns": list(IDENTITY_COLUMNS),
        "rows": [identity_values(row) for row in rows],
    }
    if not fits(json_bytes(body), limits.detail_raw, limits.detail_gzip):
        return None
    descriptor = store.write(f"detail-{prefix}", body, len(rows))
    return node_desc(
        descriptor,
        "leaf",
        prefix,
        route_mode="ordinal",
        start_ordinal=start,
        end_ordinal=end,
    )


def _identity_router(
    store: Store,
    corpus: str,
    full_sha: str,
    shards: list[dict],
    limits: Limits,
) -> dict:
    start = shards[0]["start_ordinal"]
    end = shards[-1]["end_ordinal"]
    prefix = f"{start:08x}"
    body = {
        "schema_version": 1,
        "corpus_manifest_sha256": corpus,
        "full_asset_sha256": full_sha,
        "route_kind": "detail",
        "route_mode": "ordinal",
        "prefix": prefix,
        "start_ordinal": start,
        "end_ordinal": end,
        "row_count": sum(item["row_count"] for item in shards),
        "shards": shards,
    }
    if not fits(json_bytes(body), limits.router_raw, limits.router_gzip):
        raise ValueError("Catalog identity router exceeds its cap")
    descriptor = store.write("detail-route", body, body["row_count"])
    return node_desc(
        descriptor,
        "router",
        prefix,
        route_mode="ordinal",
        start_ordinal=start,
        end_ordinal=end,
    )


def _group_identity_routes(
    store: Store,
    corpus: str,
    full_sha: str,
    shards: list[dict],
    limits: Limits,
) -> list[dict]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for shard in shards:
        trial = [*current, shard]
        start = trial[0]["start_ordinal"]
        body = {
            "schema_version": 1,
            "corpus_manifest_sha256": corpus,
            "full_asset_sha256": full_sha,
            "route_kind": "detail",
            "route_mode": "ordinal",
            "prefix": f"{start:08x}",
            "start_ordinal": start,
            "end_ordinal": trial[-1]["end_ordinal"],
            "row_count": sum(item["row_count"] for item in trial),
            "shards": trial,
        }
        if current and not fits(
            json_bytes(body), limits.router_raw, limits.router_gzip
        ):
            groups.append(current)
            current = [shard]
        else:
            current = trial
    groups.append(current)
    if len(groups) == len(shards):
        raise ValueError("Catalog identity routes cannot fit the router cap")
    return [
        _identity_router(store, corpus, full_sha, group, limits) for group in groups
    ]


def build_catalog_details(
    store: Store, corpus: str, full_sha: str, rows: list[dict], limits: Limits
) -> dict:
    """Store every compact identity once in contiguous ordinal-range leaves."""
    identities = [identity_row(row, ordinal) for ordinal, row in enumerate(rows)]
    leaves: list[dict] = []
    start = 0
    while start < len(identities):
        low, high = start + 1, len(identities)
        best: dict | None = None
        best_end = start
        while low <= high:
            middle = (low + high) // 2
            trial = {
                "schema_version": 1,
                "corpus_manifest_sha256": corpus,
                "full_asset_sha256": full_sha,
                "route_kind": "detail",
                "route_mode": "ordinal",
                "prefix": f"{start:08x}",
                "start_ordinal": start,
                "end_ordinal": middle - 1,
                "columns": list(IDENTITY_COLUMNS),
                "rows": [identity_values(row) for row in identities[start:middle]],
            }
            if not fits(json_bytes(trial), limits.detail_raw, limits.detail_gzip):
                high = middle - 1
            else:
                best_end = middle
                low = middle + 1
        if best_end == start:
            raise ValueError("One catalog identity exceeds the detail cap")
        best = _identity_leaf(
            store, corpus, full_sha, identities[start:best_end], limits
        )
        assert best is not None
        leaves.append(best)
        start = best_end
    shards = leaves
    while True:
        body = {
            "schema_version": 1,
            "corpus_manifest_sha256": corpus,
            "full_asset_sha256": full_sha,
            "route_kind": "detail",
            "route_mode": "ordinal",
            "start_ordinal": 0,
            "end_ordinal": len(rows) - 1,
            "row_count": len(rows),
            "shards": shards,
        }
        if fits(json_bytes(body), limits.router_raw, limits.router_gzip):
            return store.write("details", body, len(rows))
        shards = _group_identity_routes(store, corpus, full_sha, shards, limits)
