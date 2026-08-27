#!/usr/bin/env python3
"""Stream full archive history through a bounded-memory discovery index."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from archive import read_shard
from candidate import (
    FIELDS,
    MAX_SOURCES,
    arxiv_id,
    candidate_id,
    check_candidates,
    clause_rows,
    label_clause,
    method_signals,
    source_row,
    unsafe_text,
)
from ontology import TOPICS, TRICKS
from retrieve import (
    NOTICE,
    STOP,
    TOKEN,
    candidate_query,
    check_retrieval,
    public_row,
    retrieval_digest,
    row_text,
)
from synth import check_manifest, make_candidate


SCOPES = frozenset({"likely", "possible"})
MAX_IDEAS = 48
MAX_TRICKS = 200
MAX_SUPPORT = 6
FETCH_LIMIT = 256


def file_hash(path: Path) -> str:
    """Hash one shard without retaining its compressed bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_db(path: Path) -> sqlite3.Connection:
    """Open one disk-backed index with a deliberately small page cache."""
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=FILE;
        PRAGMA cache_size=-16384;
        PRAGMA mmap_size=0;
        CREATE TABLE seen (
            canonical TEXT PRIMARY KEY
        ) WITHOUT ROWID;
        CREATE TABLE docs (
            canonical TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            abstract TEXT NOT NULL,
            categories TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE search USING fts5(
            title,
            abstract,
            categories,
            content='docs',
            content_rowid='rowid',
            tokenize='unicode61'
        );
        CREATE TABLE trick_seen (
            label TEXT NOT NULL,
            canonical TEXT NOT NULL,
            PRIMARY KEY (label, canonical)
        ) WITHOUT ROWID;
        CREATE INDEX trick_rank ON trick_seen(label);
        CREATE TABLE trick_sources (
            label TEXT NOT NULL,
            canonical TEXT NOT NULL,
            field TEXT NOT NULL,
            start INTEGER NOT NULL,
            end INTEGER NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (label, canonical, field)
        ) WITHOUT ROWID;
        """
    )
    return db


def route_ids(paper: dict) -> tuple[set[str], set[str]]:
    """Validate and project one paper's exact ontology routes."""
    topics = paper.get("topics", [])
    tricks = paper.get("tricks", [])
    if not isinstance(topics, list) or not isinstance(tricks, list):
        raise ValueError("Promoted corpus routes are invalid")
    if not all(isinstance(row, dict) for row in [*topics, *tricks]):
        raise ValueError("Promoted corpus routes are invalid")
    topic_ids = {row.get("id") for row in topics if row.get("id")}
    trick_ids = {row.get("id") for row in tricks if row.get("id")}
    if not topic_ids <= set(TOPICS) or not trick_ids <= set(TRICKS):
        raise ValueError("Promoted corpus routes are invalid")
    return topic_ids, trick_ids


def add_pairs(
    pairs: dict[tuple[str, str], dict],
    topics: set[str],
    tricks: set[str],
    canonical: str,
    month: str,
) -> None:
    """Count every route pair while retaining only six exact supports."""
    for topic in topics:
        for trick in tricks:
            group = pairs.setdefault((topic, trick), {"count": 0, "supports": []})
            group["count"] += 1
            group["supports"].append((canonical, month))
            group["supports"].sort()
            del group["supports"][MAX_SUPPORT:]


def trim_sources(db: sqlite3.Connection, label: str, limit: int) -> None:
    """Keep the lexically first bounded evidence rows for one clause."""
    db.execute(
        """
        DELETE FROM trick_sources
        WHERE (label, canonical, field) IN (
            SELECT label, canonical, field
            FROM trick_sources
            WHERE label = ?
            ORDER BY canonical, field, start, end, text
            LIMIT -1 OFFSET ?
        )
        """,
        (label, limit),
    )


def add_source(
    db: sqlite3.Connection,
    label: str,
    canonical: str,
    field: str,
    start: int,
    end: int,
    text: str,
    limit: int,
) -> None:
    """Retain the best exact span for one paper field and clause."""
    prior = db.execute(
        """
        SELECT start, end, text FROM trick_sources
        WHERE label = ? AND canonical = ? AND field = ?
        """,
        (label, canonical, field),
    ).fetchone()
    rank = (text.casefold(), start, end, text)
    old = (
        None
        if prior is None
        else (
            prior["text"].casefold(),
            prior["start"],
            prior["end"],
            prior["text"],
        )
    )
    if old is not None and old <= rank:
        return
    db.execute(
        """
        INSERT INTO trick_sources(label, canonical, field, start, end, text)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(label, canonical, field) DO UPDATE SET
            start=excluded.start, end=excluded.end, text=excluded.text
        """,
        (label, canonical, field, start, end, text),
    )
    trim_sources(db, label, limit)


def add_tricks(
    db: sqlite3.Connection,
    paper: dict,
    canonical: str,
    limit: int,
) -> None:
    """Extract candidate clauses into exact disk-backed aggregates."""
    for field in FIELDS:
        value = paper.get(field)
        if not isinstance(value, str) or unsafe_text(value):
            continue
        for start, end, text in clause_rows(value):
            found = label_clause(text)
            if found is None:
                continue
            label, _ = found
            db.execute(
                "INSERT OR IGNORE INTO trick_seen(label, canonical) VALUES (?, ?)",
                (label, canonical),
            )
            add_source(db, label, canonical, field, start, end, text, limit)


def add_doc(db: sqlite3.Connection, paper: dict) -> None:
    """Index one privacy-filtered public projection exactly once."""
    row = public_row(paper)
    if row is None:
        return
    categories = json.dumps(
        row["categories"], ensure_ascii=False, separators=(",", ":")
    )
    cursor = db.execute(
        "INSERT INTO docs(canonical, title, abstract, categories) VALUES (?, ?, ?, ?)",
        (row["canonical_id"], row["title"], row["abstract"], categories),
    )
    db.execute(
        "INSERT INTO search(rowid, title, abstract, categories) VALUES (?, ?, ?, ?)",
        (cursor.lastrowid, row["title"], row["abstract"], categories),
    )


def scan_shards(
    db: sqlite3.Connection,
    root: Path,
    manifest: dict,
) -> tuple[int, list[str], dict[tuple[str, str], dict]]:
    """Stream digest-verified shards through constant-size route state."""
    count = 0
    loaded: list[str] = []
    pairs: dict[tuple[str, str], dict] = {}
    shards = sorted(manifest.get("shards", []), key=lambda row: row.get("month", ""))
    for shard in shards:
        month = shard.get("month")
        relative = shard.get("path")
        expected = shard.get("sha256")
        if not all(
            isinstance(value, str) and value for value in (month, relative, expected)
        ):
            raise ValueError("Promoted corpus shard metadata is invalid")
        path = root / relative
        if not path.is_file():
            continue
        if file_hash(path) != expected:
            raise ValueError(f"Promoted corpus shard drifted: {path.name}")
        payload = read_shard(path)
        loaded.append(month)
        for paper in payload["papers"]:
            if paper.get("scope") not in SCOPES:
                continue
            canonical = arxiv_id(paper.get("id"))
            inserted = db.execute(
                "INSERT OR IGNORE INTO seen(canonical) VALUES (?)", (canonical,)
            ).rowcount
            if not inserted:
                raise ValueError(f"Promoted corpus paper is duplicated: {canonical}")
            topics, tricks = route_ids(paper)
            add_pairs(pairs, topics, tricks, canonical, month)
            add_doc(db, paper)
            add_tricks(db, paper, canonical, MAX_SOURCES)
            count += 1
        db.commit()
    return count, loaded, pairs


def make_ideas(
    pairs: dict[tuple[str, str], dict],
    corpus: dict,
    limit: int,
) -> list[dict]:
    """Build bounded hypotheses from exact streamed route counts."""
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= MAX_IDEAS
    ):
        raise ValueError(f"Candidate limit must be between 1 and {MAX_IDEAS}")
    available = {row["source_id"]: row for row in corpus["source_hashes"]}
    ranked = sorted(pairs.items(), key=lambda item: (-item[1]["count"], item[0]))
    ideas = []
    for (topic, trick), group in ranked:
        if group["count"] < 2:
            continue
        supports = group["supports"]
        months = sorted({month for _, month in supports})
        hashes = [available[f"arxiv:{month}"] for month in months]
        identity = {
            "target": topic.replace("-", " "),
            "intervention": trick.replace("-", " "),
            "mechanism": "cross-paper topic-technique co-occurrence",
            "outcome": "controlled falsification signal",
        }
        ideas.append(
            make_candidate(
                corpus,
                kind="idea",
                identity=identity,
                support_ids=[canonical for canonical, _ in supports],
                source_hashes=hashes,
                retrieval=hashes,
                review_status="unreviewed",
            )
        )
        if len(ideas) == limit:
            break
    return ideas


def make_tricks(db: sqlite3.Connection, limit: int = MAX_TRICKS) -> list[dict]:
    """Materialize only the strongest clauses with bounded exact evidence."""
    ranked = db.execute(
        """
        SELECT label, COUNT(*) AS support
        FROM trick_seen
        GROUP BY label
        ORDER BY support DESC, label
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    candidates = []
    for item in ranked:
        rows = db.execute(
            """
            SELECT canonical, field, start, end, text
            FROM trick_sources
            WHERE label = ?
            ORDER BY canonical, field, start, end, text
            """,
            (item["label"],),
        ).fetchall()
        sources = [
            source_row(
                row["canonical"], row["field"], row["start"], row["end"], row["text"]
            )
            for row in rows
        ]
        signals = sorted(
            {signal for row in rows for signal in method_signals(row["text"])}
        )
        candidates.append(
            {
                "id": candidate_id(item["label"]),
                "status": "candidate",
                "kind": "unclassified",
                "label": item["label"],
                "signals": signals,
                "support_count": item["support"],
                "sources": sources,
            }
        )
    result = sorted(candidates, key=lambda row: (row["label"], row["id"]))
    check_candidates(result)
    return result


def query_terms(candidate: dict) -> Counter[str]:
    """Expand hyphenated identity terms for the FTS tokenizer."""
    text = " ".join(candidate["identity"].values()).lower().replace("-", " ")
    return Counter(term for term in TOKEN.findall(text) if term not in STOP)


def cosine(left: Counter[str], right: Counter[str]) -> float:
    """Score one bounded FTS result using transparent lexical overlap."""
    shared = left.keys() & right.keys()
    numerator = sum(left[term] * right[term] for term in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not numerator or not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def rank_one(
    db: sqlite3.Connection,
    candidate: dict,
    digest: str,
    limit: int = 12,
) -> dict:
    """Retrieve one candidate through the shared disk-backed FTS index."""
    identifier, _, excluded = candidate_query(candidate)
    query = query_terms(candidate)
    expression = " OR ".join(f'"{term}"' for term in sorted(query))
    found = db.execute(
        """
        SELECT docs.canonical, docs.title, docs.abstract, docs.categories,
               bm25(search, 3.0, 1.0, 2.0) AS rank
        FROM search JOIN docs ON docs.rowid = search.rowid
        WHERE search MATCH ?
        ORDER BY rank, docs.canonical
        LIMIT ?
        """,
        (expression, max(FETCH_LIMIT, limit * 16) + len(excluded)),
    ).fetchall()
    ranked = []
    for item in found:
        if item["canonical"] in excluded:
            continue
        row = {
            "canonical_id": item["canonical"],
            "title": item["title"],
            "abstract": item["abstract"],
            "categories": json.loads(item["categories"]),
        }
        vector = row_text(row)
        shown = round(cosine(query, vector), 6)
        if shown <= 0:
            continue
        shared = sorted(
            query.keys() & vector.keys(),
            key=lambda term: (-(query[term] * vector[term]), term),
        )[:6]
        ranked.append((shown, item["canonical"], sorted(shared)))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    result = {
        "schema_version": 1,
        "candidate_id": identifier,
        "status": "candidate_only",
        "retrieval_corpus_digest": digest,
        "candidates": [
            {
                "canonical_id": canonical,
                "score": score,
                "shared_terms": shared,
                "status": "candidate_only",
            }
            for score, canonical, shared in ranked[:limit]
        ],
        "notice": NOTICE,
    }
    result["retrieval_digest"] = retrieval_digest(result)
    return check_retrieval(result)


def make_related(
    db: sqlite3.Connection,
    candidates: list[dict],
    corpus_scope: str,
) -> dict[str, dict]:
    """Retrieve all idea queues from one shared on-disk index."""
    return {
        candidate["candidate_id"]: rank_one(db, candidate, corpus_scope)
        for candidate in candidates
    }


def trick_refs(candidates: list[dict]) -> set[tuple[str, str, int, int, str]]:
    """Flatten validated trick candidates into exact evidence references."""
    return {
        (
            source["source_id"],
            source["field"],
            source["span"][0],
            source["span"][1],
            source["text"],
        )
        for candidate in candidates
        for source in candidate["sources"]
    }


def match_shard(
    root: Path,
    shard: dict,
    by_source: dict[str, list[tuple[str, str, int, int, str]]],
    found: set[tuple[str, str, int, int, str]],
    seen: set[str],
) -> None:
    """Match requested evidence against one digest-verified archive shard."""
    relative = shard.get("path")
    expected = shard.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ValueError("Promoted corpus shard metadata is invalid")
    path = root / relative
    if not path.is_file():
        return
    if file_hash(path) != expected:
        raise ValueError(f"Promoted corpus shard drifted: {path.name}")
    for paper in read_shard(path)["papers"]:
        if paper.get("scope") not in SCOPES:
            continue
        canonical = arxiv_id(paper.get("id"))
        if canonical in seen:
            raise ValueError(f"Promoted corpus paper is duplicated: {canonical}")
        seen.add(canonical)
        for source_id, field, start, end, text in by_source.get(canonical, []):
            value = paper.get(field)
            if isinstance(value, str) and value[start:end] == text:
                found.add((source_id, field, start, end, text))


def check_trick_sources(root: Path, manifest: dict, candidates: list[dict]) -> None:
    """Resolve every trick evidence span against digest-verified archive text."""
    check_candidates(candidates)
    wanted = trick_refs(candidates)
    if not wanted:
        return
    by_source: dict[str, list[tuple[str, str, int, int, str]]] = {}
    for row in wanted:
        by_source.setdefault(row[0], []).append(row)
    found: set[tuple[str, str, int, int, str]] = set()
    seen: set[str] = set()
    for shard in sorted(
        manifest.get("shards", []), key=lambda row: row.get("month", "")
    ):
        match_shard(root, shard, by_source, found, seen)
        if found == wanted:
            return
    missing = wanted - found
    if missing:
        raise ValueError("Trick evidence does not resolve against the promoted corpus")


def scan_archive(
    root: Path,
    manifest: dict,
    corpus: dict,
    limit: int = MAX_IDEAS,
) -> dict:
    """Return discovery-compatible results with corpus-size-independent RSS."""
    check_manifest(corpus)
    with tempfile.TemporaryDirectory(prefix="atlas-scan-") as directory:
        with open_db(Path(directory) / "scan.db") as db:
            count, loaded, pairs = scan_shards(db, root, manifest)
            candidates = make_ideas(pairs, corpus, limit)
            return {
                "loaded_papers": count,
                "loaded_months": loaded,
                "candidates": candidates,
                "trick_candidates": make_tricks(db),
                "related_work": make_related(db, candidates, corpus["corpus_digest"]),
            }
