#!/usr/bin/env python3
"""Extract an uncapped, auditable method vocabulary from every corpus abstract."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from archive import MANIFEST_NAME, read_manifest, read_shard
from candidate import arxiv_id, unsafe_text
from files import atomic_write_text
from methodtext import METHOD_HEADS, PROCESS_HEADS, candidate_id, extract_methods
from ontology import TRICKS


ROOT = Path(__file__).resolve().parents[1]
VERSION = "methods-1"
NORMALIZATION = "method-phrase-1"
ASSET_NAME = "candidates.jsonl.gz"
DEFAULT_SUPPORT = 3
MAX_EVIDENCE = 6
SCOPES = ("likely", "possible", "outside")
INDEX_SCHEMA = Draft202012Validator(
    json.loads((ROOT / "schemas/methods.schema.json").read_text(encoding="utf-8"))
)
CANDIDATE_SCHEMA = Draft202012Validator(
    {"$ref": "#/$defs/candidate", "$defs": INDEX_SCHEMA.schema["$defs"]}
)


def parse_args() -> argparse.Namespace:
    """Parse one full-corpus extraction or verification request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--min-support", type=int, default=DEFAULT_SUPPORT)
    return parser.parse_args()


def file_hash(path: Path) -> str:
    """Hash one artifact without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_db(path: Path) -> sqlite3.Connection:
    """Create the bounded-memory disk aggregate used for the complete corpus."""
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    database.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=FILE;
        PRAGMA cache_size=-32768;
        PRAGMA mmap_size=0;
        CREATE TABLE seen (source_id TEXT PRIMARY KEY) WITHOUT ROWID;
        CREATE TABLE candidates (
            label TEXT PRIMARY KEY,
            head TEXT NOT NULL,
            kind TEXT NOT NULL,
            support_count INTEGER NOT NULL,
            mention_count INTEGER NOT NULL,
            first_year TEXT NOT NULL,
            last_year TEXT NOT NULL,
            likely INTEGER NOT NULL,
            possible INTEGER NOT NULL,
            outside INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE evidence (
            label TEXT NOT NULL,
            rank TEXT NOT NULL,
            source_id TEXT NOT NULL,
            published TEXT NOT NULL,
            primary_category TEXT NOT NULL,
            start INTEGER NOT NULL,
            end INTEGER NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (label, source_id)
        ) WITHOUT ROWID;
        CREATE INDEX evidence_rank ON evidence(label, rank DESC);
        """
    )
    return database


def keep_evidence(database: sqlite3.Connection, label: str, row: dict) -> None:
    """Keep six deterministic corpus-bound source examples per candidate."""
    count = database.execute(
        "SELECT COUNT(*) FROM evidence WHERE label = ?", (label,)
    ).fetchone()[0]
    if count >= MAX_EVIDENCE:
        worst = database.execute(
            "SELECT rank FROM evidence WHERE label = ? ORDER BY rank DESC LIMIT 1",
            (label,),
        ).fetchone()[0]
        if row["rank"] >= worst:
            return
    database.execute(
        """
        INSERT OR REPLACE INTO evidence
        (label, rank, source_id, published, primary_category, start, end, text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            row["rank"],
            row["source_id"],
            row["published"],
            row["primary_category"],
            row["start"],
            row["end"],
            row["text"],
        ),
    )
    database.execute(
        """
        DELETE FROM evidence WHERE label = ? AND rank = (
            SELECT rank FROM evidence WHERE label = ? ORDER BY rank DESC LIMIT 1
        ) AND (SELECT COUNT(*) FROM evidence WHERE label = ?) > ?
        """,
        (label, label, label, MAX_EVIDENCE),
    )


def add_paper(
    database: sqlite3.Connection,
    paper: dict,
    manifest_hash: str,
    extracted: list[dict] | None = None,
) -> int:
    """Add one paper's distinct normalized candidates and exact mention totals."""
    source = arxiv_id(paper["id"])
    database.execute("INSERT INTO seen(source_id) VALUES (?)", (source,))
    extracted = extract_methods(paper["abstract"]) if extracted is None else extracted
    grouped: dict[str, list[dict]] = {}
    for row in extracted:
        grouped.setdefault(row["label"], []).append(row)
    year = paper["published"][:4]
    scope = paper["scope"]
    for label, mentions in grouped.items():
        first = min(mentions, key=lambda row: (*row["span"], row["text"]))
        database.execute(
            f"""
            INSERT INTO candidates
            (label, head, kind, support_count, mention_count, first_year, last_year,
             likely, possible, outside)
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(label) DO UPDATE SET
                support_count = support_count + 1,
                mention_count = mention_count + excluded.mention_count,
                first_year = MIN(first_year, excluded.first_year),
                last_year = MAX(last_year, excluded.last_year),
                {scope} = {scope} + 1
            """,
            (
                label,
                first["head"],
                first["kind"],
                len(mentions),
                year,
                year,
                int(scope == "likely"),
                int(scope == "possible"),
                int(scope == "outside"),
            ),
        )
        start, end = first["span"]
        rank = hashlib.sha256(
            f"{manifest_hash}\0{source}\0{label}\0{start}\0{end}".encode()
        ).hexdigest()
        keep_evidence(
            database,
            label,
            {
                "rank": rank,
                "source_id": source,
                "published": paper["published"],
                "primary_category": paper["primary_category"],
                "start": start,
                "end": end,
                "text": first["text"],
            },
        )
    return len(extracted)


def candidate_row(database: sqlite3.Connection, item: sqlite3.Row) -> dict:
    """Serialize one qualified aggregate with its deterministic provenance sample."""
    evidence = database.execute(
        """
        SELECT source_id, published, primary_category, start, end, text
        FROM evidence WHERE label = ?
        ORDER BY source_id, start, end, text
        """,
        (item["label"],),
    ).fetchall()
    return {
        "id": candidate_id(item["label"]),
        "status": "corpus-extracted-candidate",
        "label": item["label"],
        "kind": item["kind"],
        "head": item["head"],
        "support_count": item["support_count"],
        "mention_count": item["mention_count"],
        "first_year": item["first_year"],
        "last_year": item["last_year"],
        "scope_counts": {scope: item[scope] for scope in SCOPES},
        "evidence": [
            {
                "source_id": row["source_id"],
                "field": "abstract",
                "span": [row["start"], row["end"]],
                "text": row["text"],
                "published": row["published"],
                "primary_category": row["primary_category"],
            }
            for row in evidence
        ],
    }


def write_candidates(database: sqlite3.Connection, path: Path, support: int) -> int:
    """Write every qualified row to deterministic compressed JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=".methods-", suffix=".tmp"
    )
    temporary = Path(name)
    count = 0
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0
            ) as stream:
                query = """
                    SELECT * FROM candidates WHERE support_count >= ?
                    ORDER BY support_count DESC, label, head
                """
                for item in database.execute(query, (support,)):
                    row = candidate_row(database, item)
                    stream.write(
                        (
                            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                        ).encode()
                    )
                    count += 1
            raw.flush()
            os.fsync(raw.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return count


def build_artifact(
    root: Path, output: Path, min_support: int = DEFAULT_SUPPORT
) -> dict:
    """Build an uncapped vocabulary from all digest-verified archive abstracts."""
    if (
        not isinstance(min_support, int)
        or isinstance(min_support, bool)
        or min_support < 1
    ):
        raise ValueError("Method candidate support must be a positive integer")
    manifest = read_manifest(root, verify_shards=False)
    shards = manifest.get("shards", [])
    source_count = manifest.get("counts", {}).get("all")
    if not isinstance(source_count, int) or not shards:
        raise ValueError("Method extraction requires a promoted corpus manifest")
    manifest_hash = file_hash(root / MANIFEST_NAME)
    curated: Counter[str] = Counter()
    scanned = mentions = quarantined = 0
    with tempfile.TemporaryDirectory() as directory:
        database = open_db(Path(directory) / "methods.sqlite")
        try:
            for shard in sorted(shards, key=lambda row: row.get("month", "")):
                path = root / shard["path"]
                if not path.is_file() or file_hash(path) != shard.get("sha256"):
                    raise ValueError(
                        f"Method source shard is missing or drifted: {path.name}"
                    )
                for paper in read_shard(path)["papers"]:
                    scanned += 1
                    curated.update({row["id"] for row in paper["tricks"]})
                    abstract = paper["abstract"]
                    unsafe = unsafe_text(abstract)
                    if unsafe:
                        quarantined += 1
                    extracted = [] if unsafe else extract_methods(abstract, prechecked=True)
                    mentions += add_paper(database, paper, manifest_hash, extracted)
                database.commit()
            distinct = database.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
            rows = write_candidates(database, output / ASSET_NAME, min_support)
        finally:
            database.close()
    if scanned != source_count:
        raise ValueError(
            "Method extraction coverage does not match the promoted corpus"
        )
    result = {
        "schema_version": 1,
        "generator_version": VERSION,
        "status": "corpus-extracted-candidates",
        "corpus": {
            "manifest_sha256": manifest_hash,
            "source_count": source_count,
            "month_count": len(shards),
        },
        "extraction": {
            "normalization_version": NORMALIZATION,
            "minimum_support": min_support,
            "maximum_evidence": MAX_EVIDENCE,
            "candidate_limit": None,
        },
        "coverage": {
            "scanned_papers": scanned,
            "scanned_abstracts": scanned,
            "quarantined_abstracts": quarantined,
            "extracted_mentions": mentions,
            "distinct_extracted_candidates": distinct,
            "qualified_candidates": rows,
        },
        "curated_families": [
            {
                "id": identifier,
                "status": "curated-family",
                "label": identifier.replace("-", " "),
                "paper_count": curated[identifier],
            }
            for identifier in sorted(TRICKS)
        ],
        "assets": [
            {
                "path": ASSET_NAME,
                "encoding": "jsonl+gzip",
                "sha256": file_hash(output / ASSET_NAME),
                "row_count": rows,
            }
        ],
        "notice": (
            "Open-vocabulary method candidates are normalized lexical extractions, "
            "not reviewed techniques, novelty claims, or evidence of effectiveness. "
            "The 24 curated technique families remain a separate navigation layer."
        ),
    }
    errors = sorted(
        INDEX_SCHEMA.iter_errors(result), key=lambda error: list(error.path)
    )
    if errors:
        raise ValueError(f"Method artifact schema is invalid: {errors[0].message}")
    atomic_write_text(
        output / "index.json",
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return result


def iter_candidates(path: Path):
    """Yield decoded candidate rows from one bounded-memory artifact asset."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Method candidate asset is invalid") from error


def check_candidate(row: object, minimum: int) -> tuple:
    """Validate recomputable candidate identity, counts, and evidence structure."""
    errors = sorted(
        CANDIDATE_SCHEMA.iter_errors(row), key=lambda error: list(error.path)
    )
    if errors:
        raise ValueError(f"Method candidate schema is invalid: {errors[0].message}")
    assert isinstance(row, dict)
    label = row["label"]
    head = row["head"]
    if (
        row["id"] != candidate_id(label)
        or row["support_count"] < minimum
        or row["mention_count"] < row["support_count"]
        or sum(row["scope_counts"].values()) != row["support_count"]
        or row["first_year"] > row["last_year"]
        or head not in METHOD_HEADS | PROCESS_HEADS
        or row["kind"]
        != ("method-noun" if head in METHOD_HEADS else "process-technique")
    ):
        raise ValueError("Method candidate semantics are invalid")
    keys = []
    for evidence in row["evidence"]:
        start, end = evidence["span"]
        found = extract_methods(evidence["text"])
        if not any(item["label"] == label and item["head"] == head for item in found):
            raise ValueError("Method candidate evidence does not reproduce its label")
        keys.append((evidence["source_id"], start, end, evidence["text"]))
    if keys != sorted(set(keys)):
        raise ValueError("Method candidate evidence is duplicated or unsorted")
    return (-row["support_count"], label, head)


def check_db(path: Path) -> sqlite3.Connection:
    """Create disk-backed identity and evidence state for artifact validation."""
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    database.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=FILE;
        PRAGMA cache_size=-16384;
        CREATE TABLE identities (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL UNIQUE
        ) WITHOUT ROWID;
        CREATE TABLE wanted (
            source_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            published TEXT NOT NULL,
            primary_category TEXT NOT NULL,
            start INTEGER NOT NULL,
            end INTEGER NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (source_id, candidate_id)
        ) WITHOUT ROWID;
        CREATE INDEX wanted_source ON wanted(source_id);
        """
    )
    return database


def record_row(database: sqlite3.Connection, row: dict) -> None:
    """Record unique identities and sampled provenance without retaining rows."""
    try:
        database.execute(
            "INSERT INTO identities(id, label) VALUES (?, ?)",
            (row["id"], row["label"]),
        )
        for evidence in row["evidence"]:
            start, end = evidence["span"]
            database.execute(
                """
                INSERT INTO wanted
                (source_id, candidate_id, published, primary_category, start, end, text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence["source_id"],
                    row["id"],
                    evidence["published"],
                    evidence["primary_category"],
                    start,
                    end,
                    evidence["text"],
                ),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("Method candidates are duplicated") from error


def verify_sources(
    root: Path, database: sqlite3.Connection, families: list[dict]
) -> None:
    """Resolve every sampled span and recompute curated-family counts from source."""
    curated: Counter[str] = Counter()
    manifest = read_manifest(root, verify_shards=False)
    for shard in sorted(manifest["shards"], key=lambda row: row["month"]):
        path = root / shard["path"]
        if not path.is_file() or file_hash(path) != shard["sha256"]:
            raise ValueError(f"Method source shard is missing or drifted: {path.name}")
        for paper in read_shard(path)["papers"]:
            curated.update({route["id"] for route in paper["tricks"]})
            source = arxiv_id(paper["id"])
            evidence_rows = database.execute(
                "SELECT * FROM wanted WHERE source_id = ?", (source,)
            ).fetchall()
            for evidence in evidence_rows:
                start, end = evidence["start"], evidence["end"]
                if (
                    paper["abstract"][start:end] != evidence["text"]
                    or paper["published"] != evidence["published"]
                    or paper["primary_category"] != evidence["primary_category"]
                ):
                    raise ValueError(
                        "Method candidate evidence does not match its source"
                    )
            database.execute("DELETE FROM wanted WHERE source_id = ?", (source,))
        database.commit()
    if database.execute("SELECT COUNT(*) FROM wanted").fetchone()[0]:
        raise ValueError("Method candidate evidence source does not resolve")
    expected = {row["id"]: row["paper_count"] for row in families}
    if expected != {identifier: curated[identifier] for identifier in sorted(TRICKS)}:
        raise ValueError("Method curated-family counts do not match the corpus")


def check_artifact(root: Path, output: Path) -> dict:
    """Strictly verify schema, provenance binding, rows, and sampled source spans."""
    try:
        value = json.loads((output / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Method artifact index is invalid") from error
    errors = sorted(INDEX_SCHEMA.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"Method artifact schema is invalid: {errors[0].message}")
    manifest = read_manifest(root, verify_shards=False)
    corpus = value["corpus"]
    if (
        corpus["manifest_sha256"] != file_hash(root / MANIFEST_NAME)
        or corpus["source_count"] != manifest.get("counts", {}).get("all")
        or corpus["month_count"] != len(manifest.get("shards", []))
        or value["coverage"]["scanned_papers"] != corpus["source_count"]
        or value["coverage"]["scanned_abstracts"] != corpus["source_count"]
        or [row["id"] for row in value["curated_families"]] != sorted(TRICKS)
    ):
        raise ValueError("Method artifact corpus coverage is invalid")
    asset = value["assets"][0]
    path = output / asset["path"]
    if not path.is_file() or file_hash(path) != asset["sha256"]:
        raise ValueError("Method candidate asset is missing or drifted")
    minimum = value["extraction"]["minimum_support"]
    with tempfile.TemporaryDirectory() as directory:
        database = check_db(Path(directory) / "check.sqlite")
        try:
            count = 0
            prior = None
            for row in iter_candidates(path):
                key = check_candidate(row, minimum)
                if prior is not None and key < prior:
                    raise ValueError(
                        "Method candidates are not deterministically ordered"
                    )
                record_row(database, row)
                prior = key
                count += 1
            database.commit()
            if (
                count != asset["row_count"]
                or count != value["coverage"]["qualified_candidates"]
            ):
                raise ValueError("Method candidate row counts disagree")
            verify_sources(root, database, value["curated_families"])
        finally:
            database.close()
    return value


def main() -> None:
    """Build or verify one full-corpus method candidate artifact."""
    args = parse_args()
    if args.check:
        value = check_artifact(args.archive, args.output)
        print(f"Validated {value['coverage']['qualified_candidates']:,} candidates")
        return
    value = build_artifact(args.archive, args.output, args.min_support)
    print(f"Built {value['coverage']['qualified_candidates']:,} candidates")


if __name__ == "__main__":
    main()
