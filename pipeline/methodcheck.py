"""Strictly verify lazy browser method assets and complete route coverage."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from methods import check_candidate
from methodtree import (
    MAX_HASH_PREFIX,
    MAX_SEARCH_PREFIX,
    MAX_PACKAGE_BYTES,
    Limits,
    compact_row,
    fits,
    id_digest,
    json_bytes,
    row_key,
    search_words,
    summary_value,
)


ROOT = Path(__file__).resolve().parents[1]
INDEX_RAW = 8 * 1024
INDEX_GZIP = 3 * 1024
SUMMARY_RAW = 32 * 1024
SUMMARY_GZIP = 10 * 1024
TOP_RAW = 128 * 1024
TOP_GZIP = 32 * 1024
TOP_COUNT = 200
MAX_HOPS = MAX_SEARCH_PREFIX + MAX_HASH_PREFIX + 2
SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/methodpack.schema.json").read_text(encoding="utf-8"))
)


def schema_check(value: object, label: str) -> None:
    """Require a generated body to match exactly one public schema variant."""
    errors = sorted(SCHEMA.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"{label} schema is invalid: {errors[0].message}")


def read_index(root: Path) -> tuple[dict, bytes]:
    """Read the stable package entry point as canonical bounded JSON."""
    path = root / "index.json"
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Method browser index is invalid") from error
    if content != json_bytes(value):
        raise ValueError("Method browser index is not canonically encoded")
    if not fits(content, INDEX_RAW, INDEX_GZIP):
        raise ValueError("Method browser index exceeds its byte cap")
    schema_check(value, "Method browser index")
    return value, content


def read_asset(
    root: Path,
    descriptor: dict,
    seen: set[str],
    stem: str,
    raw_cap: int,
    gzip_cap: int,
) -> tuple[dict, bytes]:
    """Resolve one unique content-addressed child within the package root."""
    name = descriptor["path"]
    if Path(name).name != name or not name.startswith(f"{stem}-"):
        raise ValueError("Method asset path does not match its declared role")
    if name in seen:
        raise ValueError("Method asset route is duplicated or cyclic")
    seen.add(name)
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Method browser asset is missing: {name}")
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if (
        descriptor["encoding"] != "json"
        or descriptor["bytes"] != len(content)
        or descriptor["sha256"] != digest
        or not name.endswith(f"-{digest[:16]}.json")
    ):
        raise ValueError("Method browser asset descriptor is stale")
    if not fits(content, raw_cap, gzip_cap):
        raise ValueError("Method browser child exceeds its byte cap")
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Method browser child is invalid JSON") from error
    if content != json_bytes(value):
        raise ValueError("Method browser child is not canonically encoded")
    schema_check(value, "Method browser child")
    return value, content


def node_order(node: dict) -> tuple:
    """Return the deterministic ordering key for sibling route descriptors."""
    return (
        node["prefix"],
        node.get("hash_prefix", ""),
        node.get("route_mode", ""),
        node["path"],
    )


def root_routes(body: dict, route_kind: str) -> None:
    """Require top-level routes to be sorted, distinct, and type-correct."""
    shards = body["shards"]
    if shards != sorted(shards, key=node_order):
        raise ValueError("Method routing manifest shards are not canonically ordered")
    keys = [(row["prefix"], row.get("hash_prefix", "")) for row in shards]
    if len(keys) != len(set(keys)):
        raise ValueError("Method routing manifest contains overlapping routes")
    for row in shards:
        prefix = row["prefix"]
        if route_kind == "search":
            if row.get("hash_prefix") or not prefix:
                raise ValueError("Search manifest must begin with word routes")
        elif row.get("hash_prefix") is not None or not prefix:
            raise ValueError("Detail manifest must begin with ID hash routes")


def detail_edge(parent: dict, child: dict) -> None:
    """Require one detail hash edge to advance without changing route type."""
    if child.get("hash_prefix") is not None or child.get("route_mode") == "word":
        raise ValueError("Detail routes must use only candidate hash prefixes")
    if not child["prefix"].startswith(parent["prefix"]):
        raise ValueError("Detail route prefix does not extend its parent")
    if len(child["prefix"]) <= len(parent["prefix"]):
        raise ValueError("Detail route prefix did not advance")


def search_edge(parent: dict, child: dict) -> None:
    """Require one search word or hash edge to advance deterministically."""
    if parent["route_mode"] == "word":
        if child.get("route_mode") == "hash" or child.get("hash_prefix"):
            if child["prefix"] != parent["prefix"]:
                raise ValueError("Terminal search hash route changed its word prefix")
        elif not child["prefix"].startswith(parent["prefix"]):
            raise ValueError("Search word route prefix does not extend its parent")
        elif len(child["prefix"]) <= len(parent["prefix"]):
            raise ValueError("Search word route prefix did not advance")
    else:
        if child["prefix"] != parent["prefix"]:
            raise ValueError("Search hash route changed its terminal word prefix")
        current = parent.get("hash_prefix", "")
        if not child.get("hash_prefix", "").startswith(current):
            raise ValueError("Search hash prefix does not extend its parent")
        if len(child.get("hash_prefix", "")) <= len(current):
            raise ValueError("Search hash route did not advance")


def child_rules(parent: dict, child: dict, route_kind: str) -> None:
    """Reject overlapping, backwards, or mismatched adaptive route edges."""
    if route_kind == "detail":
        detail_edge(parent, child)
    else:
        search_edge(parent, child)


def leaf_rows(
    body: dict,
    descriptor: dict,
    route_kind: str,
    minimum: int,
    details: dict[str, dict],
    searches: list[tuple[str, str, dict]],
) -> None:
    """Validate one leaf's order, identity partition, and duplicate boundary."""
    rows = body["rows"]
    if len(rows) != descriptor["row_count"]:
        raise ValueError("Method leaf row count disagrees with its descriptor")
    if rows != sorted(rows, key=row_key):
        raise ValueError("Method leaf rows are not canonically ordered")
    identities = [row["id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Method leaf contains duplicate candidates")
    if route_kind == "detail":
        for row in rows:
            check_candidate(row, minimum)
            if not id_digest(row).startswith(descriptor["prefix"]):
                raise ValueError("Detail candidate is outside its hash route")
            if row["id"] in details:
                raise ValueError("Detail candidate is reachable more than once")
            details[row["id"]] = row
        return
    prefix = descriptor["prefix"]
    hash_prefix = descriptor.get("hash_prefix", "")
    for row in rows:
        if hash_prefix and not id_digest(row).startswith(hash_prefix):
            raise ValueError("Search candidate is outside its hash subroute")
        words = tuple(
            word for word in search_words(row["label"]) if word.startswith(prefix)
        )
        if not words:
            raise ValueError("Search candidate is outside its word-prefix route")
        searches.extend((row["id"], word, row) for word in words)


def route_limits(route_kind: str, kind: str, limits: Limits) -> tuple[str, int, int]:
    """Return the filename stem and caps for one declared route node."""
    leaf = kind == "leaf"
    if route_kind == "search":
        return (
            "search" if leaf else "search-route",
            limits.search_raw if leaf else limits.router_raw,
            limits.search_gzip if leaf else limits.router_gzip,
        )
    return (
        "detail" if leaf else "detail-route",
        limits.detail_raw if leaf else limits.router_raw,
        limits.detail_gzip if leaf else limits.router_gzip,
    )


def prefix_check(descriptor: dict, route_kind: str) -> None:
    """Enforce the public search-word and detail-ID depth ceilings."""
    prefix = descriptor["prefix"]
    if route_kind == "search" and len(prefix) > MAX_SEARCH_PREFIX:
        raise ValueError("Search route exceeds its word-prefix depth cap")
    if route_kind == "detail" and len(prefix) > MAX_HASH_PREFIX:
        raise ValueError("Detail route exceeds its ID-prefix depth cap")


def walk_node(
    root: Path,
    descriptor: dict,
    route_kind: str,
    corpus: str,
    minimum: int,
    limits: Limits,
    seen: set[str],
    details: dict[str, dict],
    searches: list[tuple[str, str, dict]],
    hops: int = 0,
) -> int:
    """Traverse and validate one bounded acyclic routing subtree."""
    if hops > MAX_HOPS:
        raise ValueError("Method routing tree exceeds its depth cap")
    prefix_check(descriptor, route_kind)
    stem, raw_cap, gzip_cap = route_limits(route_kind, descriptor["kind"], limits)
    body, _ = read_asset(root, descriptor, seen, stem, raw_cap, gzip_cap)
    if (
        body["corpus_manifest_sha256"] != corpus
        or body["prefix"] != descriptor["prefix"]
    ):
        raise ValueError("Method route body is not bound to its descriptor and corpus")
    if descriptor["kind"] == "leaf":
        if route_kind == "search" and body["hash_prefix"] != descriptor.get(
            "hash_prefix", ""
        ):
            raise ValueError("Search leaf hash route disagrees with its descriptor")
        leaf_rows(body, descriptor, route_kind, minimum, details, searches)
        return len(body["rows"])
    if (
        body["route_kind"] != route_kind
        or body["route_mode"] != descriptor["route_mode"]
    ):
        raise ValueError("Method router role disagrees with its descriptor")
    if body.get("hash_prefix", "") != descriptor.get("hash_prefix", ""):
        raise ValueError("Method router hash prefix disagrees with its descriptor")
    shards = body["shards"]
    if shards != sorted(shards, key=node_order):
        raise ValueError("Method router children are not canonically ordered")
    keys = [(item["prefix"], item.get("hash_prefix", "")) for item in shards]
    if len(keys) != len(set(keys)):
        raise ValueError("Method router contains overlapping child routes")
    count = 0
    for child in shards:
        child_rules(body, child, route_kind)
        count += walk_node(
            root,
            child,
            route_kind,
            corpus,
            minimum,
            limits,
            seen,
            details,
            searches,
            hops + 1,
        )
    if count != body["row_count"] or count != descriptor["row_count"]:
        raise ValueError("Method router descendant row counts disagree")
    return count


def check_summary(value: dict, expected: dict) -> None:
    """Require every displayed aggregate to reconcile to full detail rows."""
    if value != expected:
        raise ValueError("Method summary aggregates do not reconcile")
    if sum(row["count"] for row in value["by_kind"]) != value["qualified_candidates"]:
        raise ValueError("Method kind histogram does not reconcile")
    if (
        sum(row["count"] for row in value["by_support"])
        != value["qualified_candidates"]
    ):
        raise ValueError("Method support histogram does not reconcile")
    if (
        sum(row["count"] for row in value["by_first_year"])
        != value["qualified_candidates"]
    ):
        raise ValueError("Method year histogram does not reconcile")


def check_search(
    details: dict[str, dict], searches: list[tuple[str, str, dict]]
) -> None:
    """Prove every candidate word is discoverable exactly once and unaltered."""
    expected = {
        (identifier, word)
        for identifier, row in details.items()
        for word in search_words(row["label"])
    }
    observed = Counter((identifier, word) for identifier, word, _ in searches)
    if set(observed) != expected or any(count != 1 for count in observed.values()):
        raise ValueError("Method search routes are incomplete or duplicated")
    for identifier, _, compact in searches:
        if compact != compact_row(details[identifier]):
            raise ValueError("Method search result differs from its detail candidate")


def check_package_names(root: Path, seen: set[str]) -> None:
    """Reject undeclared, embedded-full, symbolic, and non-file package entries."""
    names = {entry.name for entry in root.iterdir()}
    unsafe = any(entry.is_symlink() or not entry.is_file() for entry in root.iterdir())
    if unsafe or names != seen or "candidates.jsonl.gz" in names:
        raise ValueError("Method browser package contains stale or full default assets")


def check_pack(root: Path, limits: Limits | None = None) -> dict:
    """Verify hashes, caps, ordering, uniqueness, corpus binding, and reachability."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Method browser package must be a regular directory")
    limits = limits or Limits()
    value, _ = read_index(root)
    if sum(path.stat().st_size for path in root.iterdir()) > MAX_PACKAGE_BYTES:
        raise ValueError("Method browser package exceeds the 100 MiB Pages boundary")
    corpus = value["corpus"]["manifest_sha256"]
    minimum = value["extraction"]["minimum_support"]
    seen = {"index.json"}
    summary, _ = read_asset(
        root,
        value["assets"]["summary"],
        seen,
        "summary",
        SUMMARY_RAW,
        SUMMARY_GZIP,
    )
    top, _ = read_asset(root, value["assets"]["top"], seen, "top", TOP_RAW, TOP_GZIP)
    search, _ = read_asset(
        root,
        value["assets"]["search"],
        seen,
        "search",
        limits.router_raw,
        limits.router_gzip,
    )
    detail, _ = read_asset(
        root,
        value["assets"]["details"],
        seen,
        "details",
        limits.router_raw,
        limits.router_gzip,
    )
    for body in (summary, top, search, detail):
        if body["corpus_manifest_sha256"] != corpus:
            raise ValueError("Method browser asset corpus binding disagrees")
    if value["tier"] == "catalog-only":
        from methodcatalogcheck import verify_catalog

        verify_catalog(
            root,
            value,
            summary,
            top,
            search,
            detail,
            limits,
            seen,
            read_asset,
        )
        if value["assets"]["summary"]["row_count"] != 1:
            raise ValueError("Method summary descriptor row count disagrees")
        check_package_names(root, seen)
        return value
    details: dict[str, dict] = {}
    searches: list[tuple[str, str, dict]] = []
    root_routes(detail, "detail")
    root_routes(search, "search")
    detail_count = sum(
        walk_node(
            root,
            item,
            "detail",
            corpus,
            minimum,
            limits,
            seen,
            details,
            searches,
        )
        for item in detail["shards"]
    )
    search_count = sum(
        walk_node(
            root,
            item,
            "search",
            corpus,
            minimum,
            limits,
            seen,
            details,
            searches,
        )
        for item in search["shards"]
    )
    qualified = value["coverage"]["qualified_candidates"]
    if (
        detail_count != qualified
        or detail["row_count"] != detail_count
        or value["assets"]["details"]["row_count"] != detail_count
        or search["row_count"] != search_count
        or value["assets"]["search"]["row_count"] != search_count
        or value["assets"]["download"]["row_count"] != qualified
    ):
        raise ValueError("Method browser package row counts disagree")
    check_search(details, searches)
    ordered = sorted(details.values(), key=row_key)
    if top["rows"] != [compact_row(row) for row in ordered[:TOP_COUNT]]:
        raise ValueError("Method top rows are not the canonical candidate prefix")
    if value["assets"]["top"]["row_count"] != len(top["rows"]):
        raise ValueError("Method top descriptor row count disagrees")
    check_summary(summary, summary_value(value, ordered))
    if value["assets"]["summary"]["row_count"] != 1:
        raise ValueError("Method summary descriptor row count disagrees")
    check_package_names(root, seen)
    return value
