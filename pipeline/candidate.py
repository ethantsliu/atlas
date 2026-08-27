"""Extract auditable method-clause candidates without changing the ontology."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence

from privacy import LOCAL_PATH, PERSONAL_SOCIAL


FIELDS = ("title", "abstract")
MAX_SOURCE_CHARS = 420
MAX_LABEL_CHARS = 400
MAX_SOURCES = 12
CANDIDATE_KEYS = {
    "id",
    "status",
    "kind",
    "label",
    "signals",
    "support_count",
    "sources",
}
SOURCE_KEYS = {"source_id", "field", "span", "text"}
CLAUSE = re.compile(r"[^.!?;\n]+(?:[.!?;]|$)")
WORDS = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SPACE = re.compile(r"\s+")
MODERN_ID = re.compile(r"^\d{4}\.\d{4,5}$")
LEGACY_ID = re.compile(r"^[a-z]+(?:[.-][a-z]+)*/\d{7}$")
VERSION = re.compile(r"v\d+$", re.IGNORECASE)
PREFIX_LIMIT = 8
PREFIX = re.compile(
    r"^(?:(?:in this (?:paper|work),?\s*)?we|this (?:paper|work))\s+"
    r"(?:propose|introduce|present|develop|design)(?:s|d)?\s+",
    re.IGNORECASE,
)
SIGNALS = (
    (
        "introduction",
        re.compile(
            r"\b(?:(?:in this (?:paper|work),?\s*)?we\s+"
            r"(?:propose|introduce|present|develop|design)|"
            r"this (?:paper|work)\s+(?:proposes|introduces|presents|develops|designs))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "method-noun",
        re.compile(
            r"\b(?:method|algorithm|framework|architecture|estimator|optimizer|"
            r"procedure|technique|protocol|objective|loss function|mechanism|strategy)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "construction",
        re.compile(
            r"\b(?:using|via|based on|built (?:on|with)|consists? of)\b",
            re.IGNORECASE,
        ),
    ),
)
EMAIL = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}" r"(?![a-z0-9.-])"
)
HANDLE = re.compile(r"(?i)(?<![a-z0-9_])@[a-z0-9_]{2,32}(?![a-z0-9_])")
SOCIAL_URL = re.compile(
    r"(?i)https?://(?:www\.|mobile\.)?(?:bsky\.app|facebook\.com|github\.com|"
    r"instagram\.com|linkedin\.com|mastodon\.[a-z.]+|threads\.net|tiktok\.com|"
    r"twitter\.com|x\.com|youtube\.com|youtu\.be)/"
)
FILE_URI = re.compile(r"(?i)(?:^|[^a-z0-9])file://")
DEVICE_PATH = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:\.\.?[/\\]|~[/\\]|/(?:etc|mnt|opt|private/tmp|tmp|"
    r"var|volumes|workspace)(?:/|\b)|[a-z]:[/\\](?:users|documents and settings)"
    r"(?:[/\\]|\b))"
)
UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
POISON = (
    re.compile(
        r"\b(?:ignore|disregard|override)\s+(?:(?:all|any)\s+)?"
        r"(?:previous|prior|above|system|developer)\s+"
        r"(?:instructions?|prompts?|messages?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    re.compile(
        r"\b(?:exfiltrate|leak|steal|send|upload|transmit)\b.{0,80}"
        r"\b(?:environment variables?|env vars?|secrets?|credentials?|api keys?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:environment variables?|env vars?|secrets?|credentials?|api keys?)"
        r"\b.{0,80}\b(?:exfiltrate|leak|steal|send|upload|transmit)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:call|invoke)\s+(?:the\s+)?(?:browser\s+|shell\s+|terminal\s+|"
        r"python\s+|web\s+)?tools?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:execute|run)\s+(?:this\s+)?(?:shell\s+)?commands?\b", re.I),
    re.compile(r"\btool (?:call|request)s?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:instructs?|directs?|commands?|tells?|asks?)\s+"
        r"(?:(?:the|an?)\s+)?"
        r"(?:system|assistant|model|agent)\s+to\s+"
        r"(?:set|change|mark|override|assign|bypass)\b.{0,80}"
        r"\b(?:status|review state|score|role|kind)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:set|change|mark|override|assign)\s+(?:this\s+|the\s+)?"
        r"(?:candidate(?:'s)?\s+|record(?:'s)?\s+|item(?:'s)?\s+)?"
        r"(?:review\s+)?status\s+(?:to|as)\s+"
        r"(?:reviewed|approved|accepted|rejected|published|promoted)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:act|behave)\s+as\s+(?:an?\s+)?"
        r"(?:system|developer|administrator|admin)(?:\s+(?:agent|role))?\b|"
        r"\byou are now\s+(?:an?\s+)?"
        r"(?:system|developer|administrator|admin)(?:\s+(?:agent|role))?\b",
        re.IGNORECASE,
    ),
)


def poison_text(text: str) -> bool:
    """Quarantine a deterministic lexical set of instruction-bearing text."""
    value = unicodedata.normalize("NFKC", text)
    return any(pattern.search(value) is not None for pattern in POISON)


def unsafe_text(text: str) -> bool:
    """Detect private, instruction-bearing, or display-manipulating text."""
    value = unicodedata.normalize("NFKC", text)
    return (
        LOCAL_PATH.search(value) is not None
        or DEVICE_PATH.search(value) is not None
        or FILE_URI.search(value) is not None
        or EMAIL.search(value) is not None
        or PERSONAL_SOCIAL.search(value) is not None
        or SOCIAL_URL.search(value) is not None
        or HANDLE.search(value) is not None
        or poison_text(value)
        or any(
            unicodedata.category(character) in UNSAFE_CATEGORIES for character in text
        )
    )


def normalize(text: str) -> str:
    """Return one stable, human-readable key for a candidate clause."""
    value = unicodedata.normalize("NFKC", text).replace("–", "-").replace("—", "-")
    value = SPACE.sub(" ", value).strip(" \t\r\n.,;:!?()[]{}\"'").casefold()
    for _ in range(PREFIX_LIMIT):
        stripped = PREFIX.sub("", value, count=1)
        if stripped == value:
            return value
        value = SPACE.sub(" ", stripped).strip(" \t\r\n.,;:!?()[]{}\"'")
    # Every match removes a non-empty prefix. Inputs beyond the explicit bound
    # are rejected with an idempotent empty sentinel instead of partially named.
    return "" if PREFIX.match(value) else value


def clause_rows(text: str) -> list[tuple[int, int, str]]:
    """Split public prose while retaining exact half-open source spans."""
    rows = []
    for match in CLAUSE.finditer(text):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            rows.append((start, end, text[start:end]))
    return rows


def method_signals(text: str) -> list[str]:
    """Return conservative lexical reasons for treating a clause as methodological."""
    return [name for name, pattern in SIGNALS if pattern.search(text)]


def label_clause(text: str) -> tuple[str, list[str]] | None:
    """Return one bounded safe label and its auditable method signals."""
    if unsafe_text(text) or len(text) > MAX_SOURCE_CHARS:
        return None
    signals = method_signals(text)
    label = normalize(text)
    if not signals or len(label) > MAX_LABEL_CHARS or len(WORDS.findall(label)) < 3:
        return None
    return label, signals


def arxiv_id(value: object) -> str:
    """Canonicalize one recognized modern or legacy archive identifier."""
    if not isinstance(value, str):
        raise ValueError("Candidate extraction requires a canonical source ID")
    base = value.strip().casefold().removeprefix("arxiv:")
    base = VERSION.sub("", base)
    if not (MODERN_ID.fullmatch(base) or LEGACY_ID.fullmatch(base)):
        raise ValueError(
            "Candidate extraction requires a recognized arXiv canonical source ID"
        )
    return f"arxiv:{base}"


def source_id(record: Mapping[str, object]) -> str:
    """Read the canonical public source identity used for support accounting."""
    explicit = record.get("stable_id") or record.get("canonical_id")
    value = explicit if explicit else record.get("id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Candidate extraction requires a canonical source ID")
    if unsafe_text(value):
        raise ValueError("Candidate extraction received an unsafe source ID")
    return arxiv_id(value)


def candidate_id(label: str) -> str:
    """Bind a stable candidate ID only to its normalized clause."""
    body = f"candidate-trick-v1\0{label}".encode("utf-8")
    return f"candidate-{hashlib.sha256(body).hexdigest()[:16]}"


def source_row(
    source: str,
    field: str,
    start: int,
    end: int,
    text: str,
) -> dict:
    """Build one exact public-field provenance row."""
    return {
        "source_id": source,
        "field": field,
        "span": [start, end],
        "text": text,
    }


def require(condition: bool, message: str) -> None:
    """Raise one content-free candidate validation error."""
    if not condition:
        raise ValueError(f"Invalid trick candidates: {message}")


def check_candidates(rows: object) -> None:
    """Recompute and strictly validate emitted candidate-only rows."""
    require(isinstance(rows, list), "rows must be a list")
    row_keys = []
    ids: set[str] = set()
    labels: set[str] = set()
    for row in rows:
        require(
            isinstance(row, dict) and set(row) == CANDIDATE_KEYS,
            "candidate keys are stale",
        )
        label = row["label"]
        item_id = row["id"]
        require(
            isinstance(label, str)
            and bool(label)
            and len(label) <= MAX_LABEL_CHARS
            and label == normalize(label)
            and len(WORDS.findall(label)) >= 3
            and not unsafe_text(label),
            "candidate label is invalid",
        )
        require(
            isinstance(item_id, str) and item_id == candidate_id(label),
            "candidate ID is stale",
        )
        require(
            row["status"] == "candidate" and row["kind"] == "unclassified",
            "candidate lifecycle is invalid",
        )
        signals = row["signals"]
        require(
            isinstance(signals, list)
            and bool(signals)
            and all(isinstance(signal, str) for signal in signals)
            and signals == sorted(set(signals)),
            "candidate signals are invalid",
        )
        sources = row["sources"]
        require(
            isinstance(sources, list) and 0 < len(sources) <= MAX_SOURCES,
            "sources are missing or unbounded",
        )
        source_keys = []
        expected_signals: set[str] = set()
        source_ids: set[str] = set()
        source_fields: set[tuple[str, str]] = set()
        for source in sources:
            require(
                isinstance(source, dict) and set(source) == SOURCE_KEYS,
                "source keys are stale",
            )
            source_name = source["source_id"]
            field = source["field"]
            span = source["span"]
            text = source["text"]
            require(
                isinstance(source_name, str)
                and bool(source_name)
                and source_name == arxiv_id(source_name)
                and not unsafe_text(source_name),
                "source ID is invalid",
            )
            require(field in FIELDS, "source field is invalid")
            require(
                isinstance(span, list)
                and len(span) == 2
                and all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in span
                )
                and 0 <= span[0] < span[1],
                "source span is invalid",
            )
            require(
                isinstance(text, str)
                and bool(text)
                and len(text) <= MAX_SOURCE_CHARS
                and not unsafe_text(text)
                and span[1] - span[0] == len(text)
                and normalize(text) == label,
                "source text is inconsistent",
            )
            found = method_signals(text)
            require(bool(found), "source has no method signal")
            expected_signals.update(found)
            source_ids.add(source_name)
            source_fields.add((source_name, field))
            source_keys.append((source_name, field, span[0], span[1], text))
        require(
            len(source_fields) == len(sources) and source_keys == sorted(source_keys),
            "sources are duplicated or unsorted",
        )
        require(signals == sorted(expected_signals), "candidate signals are stale")
        support = row["support_count"]
        # Exact support may exceed the displayed papers only after the fixed
        # evidence window is full; below that boundary it remains recomputable.
        require(
            isinstance(support, int)
            and not isinstance(support, bool)
            and support >= len(source_ids)
            and (len(sources) == MAX_SOURCES or support == len(source_ids)),
            "candidate support is stale",
        )
        require(item_id not in ids and label not in labels, "candidates are duplicated")
        ids.add(item_id)
        labels.add(label)
        row_keys.append((label, item_id))
    require(row_keys == sorted(row_keys), "candidates are unsorted")


def build_candidates(records: Sequence[Mapping[str, object]]) -> list[dict]:
    """Return deterministic candidate-only method clauses with canonical support."""
    groups: dict[str, dict] = {}
    ids: dict[str, str] = {}
    for record in records:
        if record.get("record_kind") == "non_paper_context":
            continue
        source = source_id(record)
        for field in FIELDS:
            value = record.get(field)
            if not isinstance(value, str):
                continue
            if unsafe_text(value):
                continue
            for start, end, text in clause_rows(value):
                candidate = label_clause(text)
                if candidate is None:
                    continue
                label, signals = candidate
                item_id = candidate_id(label)
                prior = ids.setdefault(item_id, label)
                if prior != label:
                    raise RuntimeError("Candidate ID collision")
                group = groups.setdefault(
                    label,
                    {"signals": set(), "sources": {}},
                )
                group["signals"].update(signals)
                row = source_row(source, field, start, end, text)
                key = (source, field)
                current = group["sources"].get(key)
                rank = (text.casefold(), start, end, text)
                if current is None or rank < current[0]:
                    group["sources"][key] = (rank, row)
    candidates = []
    for label, group in groups.items():
        all_sources = [
            row
            for _, row in sorted(
                group["sources"].values(),
                key=lambda item: (
                    item[1]["source_id"],
                    item[1]["field"],
                    item[1]["span"],
                ),
            )
        ]
        support = len({row["source_id"] for row in all_sources})
        sources = all_sources[:MAX_SOURCES]
        signals = sorted(
            {signal for row in sources for signal in method_signals(row["text"])}
        )
        candidates.append(
            {
                "id": candidate_id(label),
                "status": "candidate",
                "kind": "unclassified",
                "label": label,
                "signals": signals,
                "support_count": support,
                "sources": sources,
            }
        )
    result = sorted(candidates, key=lambda item: (item["label"], item["id"]))
    check_candidates(result)
    return result
