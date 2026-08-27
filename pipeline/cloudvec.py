"""Cache and compute historical cloud embeddings."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from embed import EMBED_DIM, MODEL, MODEL_DIGEST, embed_batch, verify_model


MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
_NATIVE = None


def row_hash(identifier: str, text: str) -> str:
    """Bind one reusable vector to its paper text and pinned model."""
    body = json.dumps(
        {
            "schema": "archive-vector-v1",
            "model": MODEL,
            "digest": MODEL_DIGEST,
            "native_model": MODEL_ID,
            "native_revision": MODEL_REVISION,
            "id": identifier,
            "text": text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(body).hexdigest()


def load_cache(
    path: Path, records: list[tuple[str, str]], hashes: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Reuse unchanged rows from a resumable monthly vector cache."""
    vectors = np.zeros((len(records), EMBED_DIM), dtype=np.float32)
    done = np.zeros(len(records), dtype=bool)
    if not path.exists():
        return vectors, done
    try:
        with np.load(path) as cached:
            ids = np.asarray(cached["ids"]).astype(str)
            saved_hashes = np.asarray(cached["hashes"]).astype(str)
            saved = np.asarray(cached["vectors"], dtype=np.float32)
        if len(ids) != len(saved_hashes) or saved.shape != (len(ids), EMBED_DIM):
            return vectors, done
        indexes = {identifier: index for index, identifier in enumerate(ids)}
        for index, (identifier, _) in enumerate(records):
            saved_index = indexes.get(identifier)
            if (
                saved_index is not None
                and saved_hashes[saved_index] == hashes[index]
                and np.isfinite(saved[saved_index]).all()
                and np.linalg.norm(saved[saved_index]) > 0
            ):
                vectors[index] = saved[saved_index]
                done[index] = True
    except (OSError, ValueError, KeyError):
        pass
    return vectors, done


def save_cache(
    path: Path,
    records: list[tuple[str, str]],
    hashes: np.ndarray,
    vectors: np.ndarray,
    done: np.ndarray,
) -> None:
    """Checkpoint a monthly embedding batch atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npz")
    np.savez(
        temporary,
        ids=np.asarray([identifier for identifier, _ in records]),
        hashes=hashes,
        vectors=vectors,
        done=done,
    )
    temporary.replace(path)


def native_batch(texts: list[str]) -> np.ndarray:
    """Embed a large batch with the exact upstream MiniLM revision."""
    global _NATIVE
    if _NATIVE is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError("Native archive embedding requires cloud.txt") from error
        _NATIVE = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION)
    return np.asarray(
        _NATIVE.encode(
            texts,
            batch_size=256,
            show_progress_bar=False,
            normalize_embeddings=True,
        ),
        dtype=np.float32,
    )


def embed_records(
    month: str,
    records: list[tuple[str, str]],
    root: Path,
    batch_size: int,
    workers: int = 1,
    provider: str = "native",
) -> np.ndarray:
    """Embed one month with a row-addressable resumable checkpoint."""
    path = root / f"{month}.npz"
    hashes = np.asarray([row_hash(*record) for record in records])
    vectors, done = load_cache(path, records, hashes)
    pending = np.flatnonzero(~done)
    if len(pending) and provider == "ollama":
        verify_model()
    batches = [
        pending[start : start + batch_size]
        for start in range(0, len(pending), batch_size)
    ]

    def embed_rows(indexes: np.ndarray) -> np.ndarray:
        texts = [records[int(index)][1] for index in indexes]
        if provider == "native":
            return native_batch(texts)
        return np.asarray(embed_batch(texts), dtype=np.float32)

    def save_result(indexes: np.ndarray, result: np.ndarray) -> None:
        if result.shape != (len(indexes), EMBED_DIM):
            raise RuntimeError("Archive embedding batch has an invalid shape")
        vectors[indexes] = result
        done[indexes] = True
        save_cache(path, records, hashes, vectors, done)
        print(f"Embedded {month}: {int(done.sum()):,}/{len(records):,}", flush=True)

    if provider == "native":
        for indexes in batches:
            save_result(indexes, embed_rows(indexes))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for indexes, result in zip(
                batches, executor.map(embed_rows, batches), strict=True
            ):
                save_result(indexes, result)
    return vectors


def worker_count() -> int:
    """Read a bounded default worker count from the environment."""
    return max(1, int(os.getenv("ATLAS_EMBED_WORKERS", "1")))
