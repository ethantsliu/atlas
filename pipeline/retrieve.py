#!/usr/bin/env python3
"""Retrieve public lexical neighbors without making related-work claims."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter

from privacy import validate_public


TOKEN = re.compile(r"[a-z][a-z0-9-]{2,}")
CATEGORY = re.compile(r"\b[a-z-]+\.[a-z-]+\b", re.IGNORECASE)
MODERN_ID = re.compile(r"\d{4}\.\d{4,5}", re.IGNORECASE)
LEGACY_ID = re.compile(r"[a-z][a-z0-9.-]*/\d{7}", re.IGNORECASE)
VERSION = re.compile(r"v\d+$", re.IGNORECASE)
CANDIDATE_ID = re.compile(r"(?:idea|trick):[0-9a-f]{64}")
SHA256 = re.compile(r"[0-9a-f]{64}")
IDENTITY_KEYS = frozenset({"target", "intervention", "mechanism", "outcome"})
RETRIEVAL_KEYS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "status",
        "retrieval_corpus_digest",
        "candidates",
        "notice",
        "retrieval_digest",
    }
)
ROW_KEYS = frozenset({"canonical_id", "score", "shared_terms", "status"})
EMAIL = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"(?![a-z0-9.-])"
)
HANDLE = re.compile(r"(?i)(?<![a-z0-9_])@[a-z0-9_]{2,32}(?![a-z0-9_])")
FILE_URI = re.compile(r"(?i)(?:^|[^a-z0-9])file://")
DEVICE_PATH = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:\.\.?[/\\]|~[/\\]|/(?:etc|mnt|opt|private/tmp|tmp|"
    r"var|volumes|workspace)(?:/|\b)|[a-z]:[/\\](?:users|documents and settings)"
    r"(?:[/\\]|\b))"
)
LOCAL_URL = re.compile(
    r"(?i)https?://(?:localhost|0(?:\.0){3}|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
    r"169\.254(?:\.\d{1,3}){2}|\[?::1\]?|[a-z0-9.-]+\.(?:local|localhost))"
    r"(?::\d+)?(?:[/\s]|$)"
)
SOCIAL_URL = re.compile(
    r"(?i)https?://(?:www\.|mobile\.)?(?:bsky\.app|bitbucket\.org|discord\.com|"
    r"discord\.gg|facebook\.com|github\.com|gitlab\.com|instagram\.com|"
    r"linkedin\.com|mastodon\.[a-z.]+|medium\.com|reddit\.com|substack\.com|"
    r"t\.me|telegram\.me|threads\.net|tiktok\.com|twitch\.tv|twitter\.com|"
    r"weibo\.com|x\.com|youtube\.com|youtu\.be)/"
)
UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
STOP = {
    "and",
    "approach",
    "are",
    "based",
    "can",
    "data",
    "for",
    "from",
    "has",
    "have",
    "into",
    "large",
    "learning",
    "method",
    "methods",
    "model",
    "models",
    "neural",
    "new",
    "our",
    "paper",
    "performance",
    "propose",
    "proposed",
    "results",
    "show",
    "task",
    "tasks",
    "that",
    "the",
    "their",
    "this",
    "training",
    "use",
    "using",
    "which",
    "with",
}
NOTICE = "Lexical retrieval queue only; each result requires review."


def unsafe_text(text: str) -> bool:
    """Detect private endpoints, contact text, and invisible controls."""
    value = unicodedata.normalize("NFKC", text)
    return (
        EMAIL.search(value) is not None
        or HANDLE.search(value) is not None
        or FILE_URI.search(value) is not None
        or DEVICE_PATH.search(value) is not None
        or LOCAL_URL.search(value) is not None
        or SOCIAL_URL.search(value) is not None
        or any(
            unicodedata.category(character) in UNSAFE_CATEGORIES for character in text
        )
    )


def normalize_id(value: object) -> str | None:
    """Normalize one modern or legacy arXiv identity."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower().removeprefix("arxiv:")
    cleaned = cleaned.removesuffix(".pdf")
    cleaned = VERSION.sub("", cleaned)
    if MODERN_ID.fullmatch(cleaned) or LEGACY_ID.fullmatch(cleaned):
        return f"arxiv:{cleaned}"
    return None


def record_id(record: dict) -> str | None:
    """Read an arXiv identity without deriving it from private text."""
    for field in ("stable_id", "canonical_id", "arxiv_id", "id"):
        if identifier := normalize_id(record.get(field)):
            return identifier
    return None


def public_row(record: dict) -> dict | None:
    """Project one eligible record onto the public retrieval fields."""
    if not isinstance(record, dict):
        raise TypeError("Retrieval corpus rows must be objects")
    identifier = record_id(record)
    if (
        identifier is None
        or record.get("deleted") is True
        or record.get("status") == "deleted"
        or record.get("record_kind") == "non_paper_context"
    ):
        return None
    title = record.get("title") or ""
    abstract = record.get("abstract") or ""
    categories = record.get("categories") or []
    if not isinstance(title, str) or not isinstance(abstract, str):
        raise TypeError(f"Retrieval text is invalid for {identifier}")
    if not isinstance(categories, list) or not all(
        isinstance(category, str) for category in categories
    ):
        raise TypeError(f"Retrieval categories are invalid for {identifier}")
    if any(unsafe_text(value) for value in (title, abstract, *categories)):
        return None
    row = {
        "canonical_id": identifier,
        "title": " ".join(title.split()),
        "abstract": " ".join(abstract.split()),
        "categories": sorted(
            {category.strip() for category in categories if category.strip()}
        ),
    }
    try:
        validate_public(row, f"Retrieval row {identifier}")
    except RuntimeError:
        return None
    return row


def row_text(row: dict) -> Counter[str]:
    """Build a title-weighted public term vector."""
    title = TOKEN.findall(row["title"].lower())
    abstract = TOKEN.findall(row["abstract"].lower())
    values = [term for term in [*title, *title, *title, *abstract] if term not in STOP]
    vector = Counter(values)
    for category in row["categories"]:
        vector[f"category:{category.lower()}"] += 2
    return vector


def candidate_query(candidate: dict) -> tuple[str, Counter[str], set[str]]:
    """Project one synthesized candidate onto its public lexical identity."""
    if not isinstance(candidate, dict):
        raise TypeError("Retrieval candidate must be an object")
    identifier = candidate.get("candidate_id")
    identity = candidate.get("identity")
    supports = candidate.get("support_ids")
    if not isinstance(identifier, str) or not CANDIDATE_ID.fullmatch(identifier):
        raise ValueError("Candidate ID must be a canonical idea or trick identity")
    if not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS:
        raise ValueError("Candidate identity fields are invalid")
    if not all(
        isinstance(value, str) and bool(value.strip()) and value == value.strip()
        for value in identity.values()
    ):
        raise ValueError("Candidate identity values are invalid")
    if not isinstance(supports, list):
        raise ValueError("Candidate support IDs must be a list")
    support_ids = []
    for value in supports:
        support = normalize_id(value)
        if support is None or support != value:
            raise ValueError("Candidate support IDs must be canonical arXiv IDs")
        support_ids.append(support)
    if len(support_ids) != len(set(support_ids)):
        raise ValueError("Candidate support IDs are duplicated")
    projection = {
        "candidate_id": identifier,
        "identity": identity,
        "support_ids": sorted(support_ids),
    }
    validate_public(projection, "Retrieval candidate")
    if any(unsafe_text(value) for value in identity.values()):
        raise RuntimeError("Retrieval candidate contains unsafe text")
    text = " ".join(identity.values()).lower()
    terms = TOKEN.findall(text)
    query = Counter(term for term in terms if term not in STOP)
    for category in CATEGORY.findall(text):
        query[f"category:{category}"] += 2
    if not query:
        raise ValueError("Candidate identity has no searchable terms")
    return identifier, query, set(support_ids)


def build_corpus(records: list[dict]) -> list[dict]:
    """Deduplicate eligible arXiv rows independently of input order."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        row = public_row(record)
        if row is not None:
            grouped.setdefault(row["canonical_id"], []).append(row)
    rows = []
    for identifier in sorted(grouped):
        rows.append(
            min(
                grouped[identifier],
                key=lambda row: json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            )
        )
    return rows


def corpus_digest(rows: list[dict]) -> str:
    """Bind retrieval results to the exact normalized public corpus."""
    content = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(content).hexdigest()


def retrieval_digest(value: dict) -> str:
    """Hash every immutable retrieval field except its own digest."""
    body = {key: value[key] for key in RETRIEVAL_KEYS - {"retrieval_digest"}}
    content = json.dumps(
        body,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(content).hexdigest()


def check_row(row: object) -> dict:
    """Strictly validate one candidate-only retrieval row."""
    if not isinstance(row, dict) or set(row) != ROW_KEYS:
        raise ValueError("Retrieval candidate row fields are invalid")
    canonical = row["canonical_id"]
    if normalize_id(canonical) != canonical:
        raise ValueError("Retrieval candidate ID is not canonical")
    score = row["score"]
    if (
        not isinstance(score, float)
        or not math.isfinite(score)
        or not 0 < score <= 1
        or score != round(score, 6)
    ):
        raise ValueError("Retrieval candidate score is invalid")
    terms = row["shared_terms"]
    if (
        not isinstance(terms, list)
        or not terms
        or len(terms) > 6
        or not all(
            isinstance(term, str)
            and bool(term)
            and term == term.strip().lower()
            and not unsafe_text(term)
            for term in terms
        )
        or terms != sorted(set(terms))
    ):
        raise ValueError("Retrieval shared terms are invalid")
    if row["status"] != "candidate_only":
        raise ValueError("Retrieval candidate status is invalid")
    return row


def check_retrieval(value: object) -> dict:
    """Strictly validate and verify one immutable retrieval artifact."""
    if not isinstance(value, dict) or set(value) != RETRIEVAL_KEYS:
        raise ValueError("Retrieval artifact fields are invalid")
    if value["schema_version"] != 1:
        raise ValueError("Retrieval schema version is invalid")
    if not isinstance(value["candidate_id"], str) or not CANDIDATE_ID.fullmatch(
        value["candidate_id"]
    ):
        raise ValueError("Retrieval candidate identity is invalid")
    if value["status"] != "candidate_only" or value["notice"] != NOTICE:
        raise ValueError("Retrieval artifact status is invalid")
    if not isinstance(value["retrieval_corpus_digest"], str) or not SHA256.fullmatch(
        value["retrieval_corpus_digest"]
    ):
        raise ValueError("Retrieval corpus digest is invalid")
    rows = value["candidates"]
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Retrieval candidate rows are invalid")
    for row in rows:
        check_row(row)
    order = [(-row["score"], row["canonical_id"]) for row in rows]
    identifiers = [row["canonical_id"] for row in rows]
    if order != sorted(order) or len(identifiers) != len(set(identifiers)):
        raise ValueError("Retrieval candidates are duplicated or out of order")
    digest = value["retrieval_digest"]
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError("Retrieval artifact digest is invalid")
    if digest != retrieval_digest(value):
        raise ValueError("Retrieval artifact digest does not match its content")
    validate_public(value, "Retrieval artifact")
    return value


def term_weights(vectors: list[Counter[str]]) -> dict[str, float]:
    """Compute smoothed inverse document frequencies."""
    count = len(vectors)
    document_counts = Counter(term for vector in vectors for term in vector)
    return {
        term: math.log((count + 1) / (frequency + 1)) + 1
        for term, frequency in document_counts.items()
    }


def weighted(vector: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    """Apply logarithmic term frequency and inverse document frequency."""
    return {
        term: (1 + math.log(frequency)) * idf[term]
        for term, frequency in vector.items()
        if term in idf
    }


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    """Return cosine similarity for two sparse vectors."""
    shared = left.keys() & right.keys()
    numerator = sum(left[term] * right[term] for term in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not numerator or not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def shared_terms(
    left: dict[str, float], right: dict[str, float], limit: int = 6
) -> list[str]:
    """Expose the strongest public overlap terms in stable order."""
    ranked = sorted(
        left.keys() & right.keys(),
        key=lambda term: (-(left[term] * right[term]), term),
    )[:limit]
    return sorted(term.removeprefix("category:") for term in ranked)


def rank_candidate(
    candidate: dict,
    corpus_hash: str,
    rows: list[dict],
    vectors: list[dict[str, float]],
    idf: dict[str, float],
    limit: int,
) -> dict:
    """Rank one candidate against a prepared immutable corpus."""
    identifier, query_terms, excluded = candidate_query(candidate)
    query = weighted(query_terms, idf)

    ranked = []
    for row, vector in zip(rows, vectors, strict=True):
        canonical = row["canonical_id"]
        if canonical in excluded:
            continue
        score = cosine(query, vector)
        if score <= 0:
            continue
        shown = round(score, 6)
        if shown > 0:
            ranked.append((shown, canonical, vector))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    candidates = [
        {
            "canonical_id": canonical,
            "score": score,
            "shared_terms": shared_terms(query, vector),
            "status": "candidate_only",
        }
        for score, canonical, vector in ranked[:limit]
    ]
    result = {
        "schema_version": 1,
        "candidate_id": identifier,
        "status": "candidate_only",
        "retrieval_corpus_digest": corpus_hash,
        "candidates": candidates,
        "notice": NOTICE,
    }
    result["retrieval_digest"] = retrieval_digest(result)
    return check_retrieval(result)


def retrieve_many(
    candidates: list[dict],
    records: list[dict],
    limit: int = 12,
    *,
    corpus_scope: str | None = None,
) -> list[dict]:
    """Retrieve many candidates after preparing the public corpus once."""
    if not isinstance(candidates, list):
        raise TypeError("Retrieval candidates must be a list")
    if not isinstance(records, list):
        raise TypeError("Retrieval corpus must be a list")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("Retrieval limit must be between 1 and 100")
    if corpus_scope is not None and not SHA256.fullmatch(corpus_scope):
        raise ValueError("Retrieval corpus scope digest is invalid")
    corpus = build_corpus(records)
    counts = [row_text(row) for row in corpus]
    idf = term_weights(counts)
    vectors = [weighted(vector, idf) for vector in counts]
    digest = corpus_scope or corpus_digest(corpus)
    return [
        rank_candidate(candidate, digest, corpus, vectors, idf, limit)
        for candidate in candidates
    ]


def retrieve(
    candidate: dict,
    records: list[dict],
    limit: int = 12,
    *,
    corpus_scope: str | None = None,
) -> dict:
    """Return lexical paper candidates for one synthesized public identity."""
    return retrieve_many([candidate], records, limit, corpus_scope=corpus_scope)[0]
