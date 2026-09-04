"""Normalize auditable open-vocabulary method phrases from scholarly prose."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from candidate import clause_rows, unsafe_text


MAX_PREFIX_WORDS = 6
MAX_LABEL_CHARS = 160
WORD = re.compile(r"[^\W_][\w+/'’~-]*", re.UNICODE)
METHOD_HEADS = {
    "algorithm",
    "architecture",
    "approach",
    "estimator",
    "framework",
    "loss",
    "mechanism",
    "method",
    "objective",
    "optimizer",
    "pipeline",
    "procedure",
    "protocol",
    "strategy",
    "technique",
}
PROCESS_HEADS = {
    "adaptation",
    "attention",
    "augmentation",
    "clustering",
    "compression",
    "decoding",
    "distillation",
    "embedding",
    "estimation",
    "fine tuning",
    "inference",
    "learning",
    "normalization",
    "optimization",
    "pretraining",
    "pruning",
    "quantization",
    "ranking",
    "regularization",
    "retrieval",
    "routing",
    "sampling",
    "search",
    "segmentation",
    "training",
}
HEAD_FORMS = {
    **{head: head for head in METHOD_HEADS | PROCESS_HEADS},
    **{f"{head}s": head for head in METHOD_HEADS},
    "approaches": "approach",
    "architectures": "architecture",
    "losses": "loss",
    "mechanisms": "mechanism",
    "strategies": "strategy",
    "fine-tuning": "fine tuning",
    "finetuning": "fine tuning",
}
HEAD = re.compile(
    r"\b(?:"
    + "|".join(
        sorted((re.escape(value) for value in HEAD_FORMS), key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)
BOUNDARY = {
    "a",
    "an",
    "are",
    "as",
    "at",
    "by",
    "called",
    "develop",
    "developed",
    "develops",
    "employ",
    "employed",
    "employs",
    "for",
    "from",
    "has",
    "have",
    "introduce",
    "introduced",
    "introduces",
    "is",
    "of",
    "on",
    "our",
    "present",
    "presented",
    "presents",
    "propose",
    "proposed",
    "proposes",
    "use",
    "used",
    "uses",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "to",
    "using",
    "via",
    "we",
    "with",
}
GENERIC = {
    "art",
    "baseline",
    "both",
    "common",
    "conventional",
    "current",
    "different",
    "effective",
    "efficient",
    "existing",
    "flexible",
    "general",
    "generic",
    "new",
    "novel",
    "of",
    "one",
    "previous",
    "prior",
    "promising",
    "proposed",
    "robust",
    "scalable",
    "standard",
    "state",
    "several",
    "such",
    "simple",
    "the",
    "three",
    "traditional",
    "two",
    "unified",
    "various",
}


def clean_token(value: str) -> str:
    """Normalize one phrase token for punctuation-insensitive deduplication."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("’", "'").replace("-", " ").replace("~", " ")
    return " ".join(WORD.findall(value))


def head_value(value: str) -> str | None:
    """Map one observed technique head to its canonical singular spelling."""
    return HEAD_FORMS.get(" ".join(clean_token(value).split()))


def phrase_label(text: str, head: str) -> str | None:
    """Return the stable label for one exact source phrase."""
    words = [clean_token(match.group()) for match in WORD.finditer(text)]
    tokens = [token for word in words for token in word.split()]
    if not tokens:
        return None
    canonical = head_value(" ".join(tokens[-2:])) or head_value(tokens[-1])
    if canonical != head:
        return None
    prefix = tokens[: -len(canonical.split())]
    while prefix and prefix[0] in GENERIC:
        prefix.pop(0)
    if not prefix:
        return None
    label = " ".join([*prefix, canonical])
    meaningful = [token for token in prefix if token not in GENERIC]
    if (
        not label
        or len(label) > MAX_LABEL_CHARS
        or len(label.split()) > MAX_PREFIX_WORDS + 2
        or head in METHOD_HEADS
        and not meaningful
    ):
        return None
    return label


def phrase_start(clause: str, start: int) -> int:
    """Find the bounded modifier phrase immediately preceding one method head."""
    tokens = list(WORD.finditer(clause[:start]))
    chosen = []
    prior = start
    for token in reversed(tokens):
        gap = clause[token.end() : prior]
        if gap.strip() or clean_token(token.group()) in BOUNDARY:
            break
        chosen.append(token)
        prior = token.start()
        if len(chosen) == MAX_PREFIX_WORDS:
            break
    return chosen[-1].start() if chosen else start


def extract_methods(abstract: str, *, prechecked: bool = False) -> list[dict]:
    """Extract normalized open-vocabulary phrases with exact abstract spans."""
    if (
        not isinstance(abstract, str)
        or not abstract
        or (not prechecked and unsafe_text(abstract))
    ):
        return []
    rows = []
    for clause_start, _, clause in clause_rows(abstract):
        for match in HEAD.finditer(clause):
            head = head_value(match.group())
            if head is None:
                continue
            following = WORD.search(clause, match.end())
            if (
                following is not None
                and not clause[match.end() : following.start()].strip()
                and head_value(following.group()) is not None
            ):
                continue
            start = phrase_start(clause, match.start())
            end = match.end()
            text = clause[start:end]
            label = phrase_label(text, head)
            if label is None:
                continue
            rows.append(
                {
                    "label": label,
                    "head": head,
                    "kind": (
                        "method-noun" if head in METHOD_HEADS else "process-technique"
                    ),
                    "span": [clause_start + start, clause_start + end],
                    "text": text,
                }
            )
    return rows


def candidate_id(label: str) -> str:
    """Create an identity that is independent of corpus and support changes."""
    digest = hashlib.sha256(f"method-candidate-1\0{label}".encode()).hexdigest()
    return f"method-candidate:{digest}"
