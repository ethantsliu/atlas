#!/usr/bin/env python3
"""Build compact semantic coordinates for the public atlas graph."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from cluster import build_clusters
from layout import (
    EMBED_DIM as DEFAULT_DIM,
    LAYOUT_METHOD,
    MODEL_CONTEXT,
    MODEL_DIGEST as DEFAULT_DIGEST,
    MODEL_NAME,
    OLLAMA_VERSION,
    REDUCER,
)
from semantic import (
    NEIGHBOR_COUNT,
    ensure_quality,
    quality_report,
    semantic_neighbors,
)

ROOT = Path(__file__).resolve().parents[1]
ATLAS_PATH = ROOT / "data/generated/atlas.json"
LAYOUT_PATH = ROOT / "data/generated/layout.json"
CACHE_PATH = ROOT / "data/cache/vectors.npz"
PART_PATH = ROOT / "data/cache/parts.npz"
DETAILS_PATH = ROOT / "data/reviewed/readings"
MODEL = os.environ.get("ATLAS_EMBED_MODEL", MODEL_NAME)
MODEL_DIGEST = os.environ.get("ATLAS_EMBED_DIGEST", DEFAULT_DIGEST)
EMBED_DIM = int(os.environ.get("ATLAS_EMBED_DIM", str(DEFAULT_DIM)))
ENDPOINT = os.environ.get("ATLAS_EMBED_URL", "http://127.0.0.1:11434/api/embed")
EMBED_WORKERS = max(1, int(os.environ.get("ATLAS_EMBED_WORKERS", "1")))
TAGS_ENDPOINT = os.environ.get(
    "ATLAS_TAGS_URL",
    f"{ENDPOINT.rsplit('/api/', 1)[0]}/api/tags",
)
SHOW_ENDPOINT = os.environ.get(
    "ATLAS_SHOW_URL",
    f"{ENDPOINT.rsplit('/api/', 1)[0]}/api/show",
)
VERSION_ENDPOINT = os.environ.get(
    "ATLAS_VERSION_URL",
    f"{ENDPOINT.rsplit('/api/', 1)[0]}/api/version",
)


def route_names(item: dict) -> str:
    routes = [*item.get("topics", []), *item.get("tricks", [])]
    return ", ".join(route.get("id", "") for route in routes)


PLACEHOLDERS = (
    "full reading has not yet been completed",
    "collection currently provides only title-level evidence",
    "no abstract or result passage is available locally",
)


def clip_words(value: object, limit: int) -> str:
    """Clip normalized prose at a word boundary within a field budget."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    clipped = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return clipped or text[:limit]


def detail_text(detail: dict) -> str:
    """Budget every reviewed field so later semantic signals survive."""
    method = detail.get("method", {})
    techniques = ", ".join(
        str(item.get("id", "")) for item in detail.get("techniques", [])[:6]
    )
    return " ".join(
        part
        for part in (
            f"question: {clip_words(detail.get('question'), 100)}",
            f"core idea: {clip_words(method.get('core_idea'), 170)}",
            f"mechanism: {clip_words(method.get('mechanism'), 170)}",
            f"techniques: {clip_words(techniques, 70)}",
        )
        if part.split(": ", 1)[-1]
    )


def paper_text(paper: dict, detail: dict | None = None) -> str:
    reading = paper.get("reading", {})
    reviewed = detail_text(detail) if detail else ""
    compact = " ".join(str(reading.get(key, "")) for key in ("problem", "approach"))
    if any(phrase in compact.casefold() for phrase in PLACEHOLDERS):
        compact = ""
    prefix = (
        "collection entry"
        if paper.get("record_kind") == "non_paper_context"
        else "research paper"
    )
    return " ".join(
        part
        for part in (
            f"{prefix}: {clip_words(paper['title'], 160)}",
            reviewed or compact,
            f"areas: {clip_words(route_names(paper), 70)}",
        )
        if part.split(": ", 1)[-1]
    )


def idea_text(idea: dict) -> str:
    brief = idea.get("brief", {})
    methods = " ".join(str(item) for item in brief.get("method", [])[:2])
    routes = ", ".join([*idea.get("topic_ids", []), *idea.get("trick_ids", [])])
    return " ".join(
        part
        for part in (
            f"research idea: {clip_words(brief.get('title'), 180)}",
            f"thesis: {clip_words(brief.get('thesis'), 250)}",
            f"proposed method: {clip_words(methods, 250)}",
            f"areas: {clip_words(routes, 80)}",
        )
        if part.split(": ", 1)[-1]
    )


def taxon_text(item: dict, prefix: str) -> str:
    """Describe a curated taxonomy marker without corpus-order examples."""
    return f"{prefix}: {item['label']}"


def node_records(
    atlas: dict,
    details: dict[str, dict] | None = None,
) -> list[tuple[str, str]]:
    topics = [
        (
            f"topic:{item['id']}",
            taxon_text(item, "machine learning research area"),
        )
        for item in atlas["topics"]
    ]
    tricks = [
        (
            f"trick:{item['id']}",
            taxon_text(item, "machine learning method"),
        )
        for item in atlas["tricks"]
    ]
    details = details or {}
    papers = [
        (item["id"], paper_text(item, details.get(item.get("stable_id", ""))))
        for item in atlas["papers"]
    ]
    ideas = [(item["id"], idea_text(item)) for item in atlas["ideas"]]
    return [*topics, *tricks, *papers, *ideas]


def load_details() -> dict[str, dict]:
    """Load authoritative reviewed semantic inputs keyed by canonical paper ID."""
    details: dict[str, dict] = {}
    for path in sorted(DETAILS_PATH.glob("*.json")):
        detail = json.loads(path.read_text(encoding="utf-8"))
        stable_id = detail.get("stable_id")
        if stable_id:
            details[stable_id] = detail
    return details


def embed_batch(texts: list[str]) -> list[list[float]]:
    body = json.dumps(
        {
            "model": MODEL,
            "input": texts,
            "truncate": False,
            "options": {"num_ctx": MODEL_CONTEXT},
        }
    ).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            embeddings = json.load(response)["embeddings"]
    except (urllib.error.URLError, TimeoutError, KeyError) as error:
        raise RuntimeError(
            f"Embedding failed; run `ollama pull {MODEL}` and start Ollama"
        ) from error
    try:
        vectors = np.asarray(embeddings, dtype=np.float32)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Embedding model returned invalid vectors") from error
    if (
        vectors.ndim != 2
        or not np.isfinite(vectors).all()
        or np.any(np.linalg.norm(vectors, axis=1) == 0)
    ):
        raise RuntimeError("Embedding model returned invalid vectors")
    return embeddings


def verify_model() -> None:
    """Require the configured model name to resolve to its pinned artifact."""
    try:
        with urllib.request.urlopen(TAGS_ENDPOINT, timeout=15) as response:
            models = json.load(response).get("models", [])
        with urllib.request.urlopen(VERSION_ENDPOINT, timeout=15) as response:
            version = json.load(response).get("version")
        show_request = urllib.request.Request(
            SHOW_ENDPOINT,
            data=json.dumps({"model": MODEL}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(show_request, timeout=30) as response:
            model_info = json.load(response).get("model_info", {})
    except (urllib.error.URLError, KeyError) as error:
        raise RuntimeError("Could not verify the embedding model artifact") from error
    matches = [
        item
        for item in models
        if item.get("name") in {MODEL, f"{MODEL}:latest"}
        or item.get("model") in {MODEL, f"{MODEL}:latest"}
    ]
    if not matches or matches[0].get("digest") != MODEL_DIGEST:
        raise RuntimeError(f"Embedding model {MODEL} does not match its pinned digest")
    if version != OLLAMA_VERSION:
        raise RuntimeError(f"Ollama {version} does not match {OLLAMA_VERSION}")
    if model_info.get("bert.context_length", 0) < MODEL_CONTEXT:
        raise RuntimeError(
            "Embedding model context is below the pinned request context"
        )


def load_parts(
    records: list[tuple[str, str]],
    digest: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Resume only an exact, structurally valid embedding checkpoint."""
    vectors = np.zeros((len(records), EMBED_DIM), dtype=np.float32)
    done = np.zeros(len(records), dtype=bool)
    if not PART_PATH.exists():
        return vectors, done
    with np.load(PART_PATH) as partial:
        saved_ids = partial["ids"]
        saved_vectors = partial["vectors"]
        saved_done = partial["done"]
        saved_hashes = partial["row_hashes"] if "row_hashes" in partial.files else []
        if not (
            saved_vectors.shape == (len(saved_ids), EMBED_DIM)
            and saved_done.shape == (len(saved_ids),)
            and len(saved_hashes) == len(saved_ids)
            and len({str(node_id) for node_id in saved_ids}) == len(saved_ids)
        ):
            return vectors, done
        saved_indexes = {str(node_id): index for index, node_id in enumerate(saved_ids)}
        for index, record in enumerate(records):
            saved_index = saved_indexes.get(record[0])
            if (
                saved_index is not None
                and bool(saved_done[saved_index])
                and str(saved_hashes[saved_index]) == row_hash(record)
            ):
                vectors[index] = saved_vectors[saved_index]
                done[index] = True
    completed = vectors[done]
    if completed.size and (
        not np.isfinite(completed).all()
        or np.any(np.linalg.norm(completed, axis=1) == 0)
    ):
        return np.zeros_like(vectors), np.zeros_like(done)
    return vectors, done


def save_parts(
    records: list[tuple[str, str]],
    digest: str,
    vectors: np.ndarray,
    done: np.ndarray,
) -> None:
    """Atomically checkpoint aligned vectors and their completion mask."""
    PART_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PART_PATH.with_suffix(".tmp.npz")
    np.savez_compressed(
        temp_path,
        digest=digest,
        ids=np.asarray([node_id for node_id, _ in records]),
        row_hashes=np.asarray([row_hash(record) for record in records]),
        vectors=vectors,
        done=done,
    )
    os.replace(temp_path, PART_PATH)


def embed_all(
    records: list[tuple[str, str]],
    digest: str,
    batch_size: int = 64,
) -> np.ndarray:
    vectors, done = load_parts(records, digest)
    pending = np.flatnonzero(~done)
    if not len(pending):
        return vectors
    verify_model()
    batches = [
        pending[start : start + batch_size]
        for start in range(0, len(pending), batch_size)
    ]

    def embed_rows(indexes: np.ndarray) -> np.ndarray:
        texts = [records[int(index)][1] for index in indexes]
        return np.asarray(embed_batch(texts), dtype=np.float32)

    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as executor:
        results = executor.map(embed_rows, batches)
        for indexes, result in zip(batches, results, strict=True):
            if result.shape != (len(indexes), EMBED_DIM):
                raise RuntimeError("Embedding batch has an unexpected shape")
            if not np.isfinite(result).all() or np.any(
                np.linalg.norm(result, axis=1) == 0
            ):
                raise RuntimeError("Embedding batch contains invalid vectors")
            vectors[indexes] = result
            done[indexes] = True
            save_parts(records, digest, vectors, done)
            print(f"Embedded {int(done.sum()):,}/{len(records):,}", flush=True)
    return vectors


def reduce_points(vectors: np.ndarray) -> np.ndarray:
    import umap

    reducer = umap.UMAP(
        n_components=REDUCER["dimensions"],
        n_neighbors=REDUCER["neighbors"],
        min_dist=REDUCER["min_dist"],
        metric=REDUCER["metric"],
        random_state=REDUCER["random_seed"],
        transform_seed=REDUCER["random_seed"],
        n_jobs=1,
    )
    points = reducer.fit_transform(vectors)
    points -= np.median(points, axis=0, keepdims=True)
    scale = np.percentile(np.abs(points), REDUCER["scale_percentile"], axis=0)
    if not np.isfinite(points).all() or not np.all(scale > 0):
        raise RuntimeError("Semantic reducer produced a degenerate projection")
    return (
        np.clip(points / scale, -REDUCER["clip"], REDUCER["clip"]) * REDUCER["extent"]
    )


def vector_hash(records: list[tuple[str, str]]) -> str:
    """Hash semantic text and the immutable embedding-service contract."""
    inputs = {
        "schema": "semantic-vectors-v3",
        "embedding": {
            "provider": "ollama",
            "api": "embed-v1",
            "model": MODEL,
            "artifact_sha256": MODEL_DIGEST,
            "dimensions": EMBED_DIM,
            "context_length": MODEL_CONTEXT,
            "runtime": f"ollama-{OLLAMA_VERSION}",
            "text_schema": "field-budget-v1",
            "truncate": False,
        },
        "records": records,
    }
    body = json.dumps(inputs, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def row_hash(record: tuple[str, str]) -> str:
    """Bind one checkpoint row to its ID, text, and embedding contract."""
    inputs = {
        "schema": "semantic-vector-row-v1",
        "embedding": {
            "provider": "ollama",
            "api": "embed-v1",
            "model": MODEL,
            "artifact_sha256": MODEL_DIGEST,
            "dimensions": EMBED_DIM,
            "context_length": MODEL_CONTEXT,
            "runtime": f"ollama-{OLLAMA_VERSION}",
            "text_schema": "field-budget-v1",
            "truncate": False,
        },
        "record": record,
    }
    body = json.dumps(inputs, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def input_hash(records: list[tuple[str, str]], vector_sha256: str) -> str:
    """Hash the immutable vectors plus every deterministic reducer parameter."""
    inputs = {
        "schema": "semantic-layout-v3",
        "embedding_input_sha256": vector_hash(records),
        "vector_sha256": vector_sha256,
        "reducer": REDUCER,
    }
    body = json.dumps(inputs, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def vector_sha(vectors: np.ndarray) -> str:
    """Hash canonical little-endian float32 bytes for reproducible provenance."""
    canonical = np.ascontiguousarray(vectors, dtype="<f4")
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def valid_vectors(vectors: np.ndarray, expected_sha: str) -> bool:
    """Reject malformed, degenerate, or byte-drifted cached embeddings."""
    return (
        vectors.ndim == 2
        and vectors.dtype == np.float32
        and vectors.shape[1] == EMBED_DIM
        and np.isfinite(vectors).all()
        and np.all(np.linalg.norm(vectors, axis=1) > 0)
        and vector_sha(vectors) == expected_sha
    )


def save_cache(digest: str, vectors: np.ndarray) -> None:
    """Atomically persist a complete, self-verifying embedding cache."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CACHE_PATH.with_suffix(".tmp.npz")
    np.savez_compressed(
        temp_path,
        digest=digest,
        model=MODEL,
        model_digest=MODEL_DIGEST,
        dimensions=EMBED_DIM,
        reducer=json.dumps(REDUCER, sort_keys=True),
        vector_sha256=vector_sha(vectors),
        vectors=vectors,
    )
    os.replace(temp_path, CACHE_PATH)


def load_vectors(records: list[tuple[str, str]]) -> np.ndarray:
    digest = vector_hash(records)
    if CACHE_PATH.exists():
        with np.load(CACHE_PATH) as cached:
            vectors = cached["vectors"]
            expected_sha = (
                str(cached["vector_sha256"]) if "vector_sha256" in cached.files else ""
            )
            if (
                str(cached["digest"]) == digest
                and vectors.shape[0] == len(records)
                and valid_vectors(vectors, expected_sha)
            ):
                print(f"Loaded {len(records):,} cached embeddings")
                return vectors
    vectors = embed_all(records, digest)
    if vectors.shape != (len(records), EMBED_DIM):
        raise RuntimeError(
            f"Embedding model returned {vectors.shape}, expected "
            f"({len(records)}, {EMBED_DIM})"
        )
    save_cache(digest, vectors)
    if PART_PATH.exists():
        PART_PATH.unlink()
    return vectors


def alias_exclusions(
    atlas: dict,
    records: list[tuple[str, str]],
) -> dict[str, set[str]]:
    """Group canonical-paper aliases and nodes with identical semantic text."""
    groups: dict[str, set[str]] = {}
    for node_id, text in records:
        normalized = " ".join(text.casefold().split())
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        groups.setdefault(f"text:{digest}", set()).add(node_id)
    for paper in atlas["papers"]:
        canonical_id = paper.get("stable_id")
        if canonical_id:
            groups.setdefault(f"paper:{canonical_id}", set()).add(paper["id"])
    excluded: dict[str, set[str]] = {}
    for group in groups.values():
        if len(group) > 1:
            for node_id in group:
                excluded.setdefault(node_id, set()).update(group - {node_id})
    return excluded


def cohort_ids(atlas: dict, records: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Define exact graph cohorts for projection-fidelity reporting."""
    all_ids = {node_id for node_id, _ in records}
    paper_ids = {
        item["id"]
        for item in atlas["papers"]
        if item.get("record_kind") != "non_paper_context"
    }
    context_ids = {item["id"] for item in atlas["papers"]} - paper_ids
    idea_ids = {item["id"] for item in atlas["ideas"]}
    return {
        "all": all_ids,
        "paper": paper_ids,
        "context": context_ids,
        "idea": idea_ids,
        "taxonomy": all_ids - paper_ids - context_ids - idea_ids,
    }


def build_layout(atlas: dict, details: dict[str, dict] | None = None) -> dict:
    records = node_records(atlas, details)
    vectors = load_vectors(records)
    points = reduce_points(vectors)
    points = np.round(points, 3)
    exclusions = alias_exclusions(atlas, records)
    quality = quality_report(
        records,
        vectors,
        points,
        cohort_ids(atlas, records),
        exclusions=exclusions,
    )
    ensure_quality(quality)
    positions = {
        node_id: [float(value) for value in point]
        for (node_id, _), point in zip(records, points, strict=True)
    }
    cluster_fields = build_clusters(records, vectors, points)
    vectors_sha = vector_sha(vectors)
    return {
        "schema_version": 3,
        "model": MODEL,
        "embedding": {
            "provider": "ollama",
            "api": "embed-v1",
            "model": MODEL,
            "artifact_sha256": MODEL_DIGEST,
            "dimensions": EMBED_DIM,
            "context_length": MODEL_CONTEXT,
            "metric": "cosine",
            "runtime": f"ollama-{OLLAMA_VERSION}",
            "text_schema": "field-budget-v1",
            "truncate": False,
            "input_sha256": vector_hash(records),
            "vector_sha256": vectors_sha,
        },
        "method": LAYOUT_METHOD,
        "reducer": REDUCER,
        "input_sha256": input_hash(records, vectors_sha),
        "node_count": len(records),
        "quality": quality,
        "neighbor_count": NEIGHBOR_COUNT,
        "neighbors": semantic_neighbors(
            records,
            vectors,
            exclusions=exclusions,
        ),
        **cluster_fields,
        "positions": positions,
    }


def main() -> None:
    atlas = json.loads(ATLAS_PATH.read_text(encoding="utf-8"))
    layout = build_layout(atlas, load_details())
    LAYOUT_PATH.write_text(
        json.dumps(layout, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Built semantic layout for {layout['node_count']:,} nodes with {MODEL}")


if __name__ == "__main__":
    main()
