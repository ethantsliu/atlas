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
PROCESS_PLURALS = {
    "adaptations": "adaptation",
    "attentions": "attention",
    "augmentations": "augmentation",
    "clusterings": "clustering",
    "compressions": "compression",
    "decodings": "decoding",
    "distillations": "distillation",
    "embeddings": "embedding",
    "estimations": "estimation",
    "inferences": "inference",
    "normalizations": "normalization",
    "optimizations": "optimization",
    "pretrainings": "pretraining",
    "prunings": "pruning",
    "quantizations": "quantization",
    "rankings": "ranking",
    "regularizations": "regularization",
    "retrievals": "retrieval",
    "routings": "routing",
    "samplings": "sampling",
    "searches": "search",
    "segmentations": "segmentation",
}
WRAPPER_HEADS = frozenset({"approach", "framework", "method"})
NOISE_LABELS = frozenset(
    {
        "during training",
        "few training",
        "mass loss",
        "most existing method",
        "physical mechanism",
        "resulting framework",
    }
)
HEAD_FORMS = {
    **{head: head for head in METHOD_HEADS | PROCESS_HEADS},
    **{f"{head}s": head for head in METHOD_HEADS},
    **PROCESS_PLURALS,
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
    "and",
    "are",
    "as",
    "at",
    "by",
    "but",
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
    "nor",
    "of",
    "on",
    "or",
    "our",
    "plus",
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
    two = head_value(" ".join(tokens[-2:])) if len(tokens) >= 2 else None
    one = head_value(tokens[-1])
    if two == head:
        width = 2
    elif one == head:
        width = 1
    else:
        return None
    prefix = tokens[:-width]
    while prefix and prefix[0] in GENERIC:
        prefix.pop(0)
    if not prefix:
        return None
    label = " ".join([*prefix, head])
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


def unwrap_process(
    clause: str, start: int, end: int, head: str
) -> tuple[str, str] | None:
    """Canonicalize a direct generic wrapper around one process phrase."""
    if head not in WRAPPER_HEADS:
        return None
    prefix = clause[start:end]
    matches = list(HEAD.finditer(prefix))
    if not matches:
        return None
    inner = matches[-1]
    inner_head = head_value(inner.group())
    if (
        inner_head not in PROCESS_HEADS
        or prefix[inner.end() :].strip()
        or (label := phrase_label(prefix[: inner.end()], inner_head)) is None
    ):
        return None
    return label, inner_head


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
            unwrapped = unwrap_process(clause, start, match.start(), head)
            if unwrapped is not None:
                label, head = unwrapped
            if label in NOISE_LABELS:
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
