"""Build and validate compact support-paper lineage bundles."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

from archive import read_shard
from rules import check


SCHEMA_VERSION = 1
ROOT_FIELDS = {"schema_version", "corpus_digest", "content_sha256", "papers"}
PAPER_FIELDS = {"canonical_id", "title", "url", "published", "archive"}
ARCHIVE_FIELDS = {"month", "path", "sha256", "row"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MONTH = re.compile(r"^\d{4}-\d{2}$")
MODERN_ID = re.compile(r"^\d{4}\.\d{4,5}$")
LEGACY_ID = re.compile(r"^[a-z]+(?:[.-][a-z]+)*/\d{7}$")
EMAIL = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"(?![a-z0-9.-])"
)
HANDLE = re.compile(r"(?i)(?<![a-z0-9_])@[a-z0-9_]{2,32}(?![a-z0-9_])")
FILE_URI = re.compile(r"(?i)(?:^|[^a-z0-9])file://")
DEVICE_PATH = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:\.\.?[/\\]|~[/\\]|/(?:etc|home|mnt|opt|private|"
    r"root|tmp|users|var|volumes|workspace)(?:/|\b)|[a-z]:[/\\](?:users|"
    r"documents and settings)(?:[/\\]|\b))"
)
SOCIAL_URL = re.compile(
    r"(?i)https?://(?:www\.|mobile\.)?(?:bsky\.app|bitbucket\.org|discord\.com|"
    r"discord\.gg|facebook\.com|github\.com|gitlab\.com|instagram\.com|"
    r"linkedin\.com|mastodon\.[a-z.]+|medium\.com|reddit\.com|substack\.com|"
    r"t\.me|telegram\.me|threads\.net|tiktok\.com|twitch\.tv|twitter\.com|"
    r"weibo\.com|x\.com|youtube\.com|youtu\.be)/"
)
PRIVATE_REPO = re.compile(
    r"(?i)\b(?:private[-_ ]?repo(?:sitory)?|[a-z0-9]+[-_]overleaf)\b"
)
UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
MAX_TITLE = 512


def json_bytes(value: object) -> bytes:
    """Serialize semantic JSON deterministically for hashing and publication."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def corpus_digest(value: object) -> str:
    """Hash the exact corpus-generation input without key-order sensitivity."""
    return hashlib.sha256(json_bytes(value)).hexdigest()


def content_digest(bundle: dict) -> str:
    """Hash every public bundle field except the self-describing digest."""
    payload = {key: value for key, value in bundle.items() if key != "content_sha256"}
    return hashlib.sha256(json_bytes(payload)).hexdigest()


def unsafe_title(title: str) -> bool:
    """Detect device identity, contact data, and display-manipulating text."""
    value = unicodedata.normalize("NFKC", title)
    return (
        DEVICE_PATH.search(value) is not None
        or FILE_URI.search(value) is not None
        or EMAIL.search(value) is not None
        or HANDLE.search(value) is not None
        or SOCIAL_URL.search(value) is not None
        or PRIVATE_REPO.search(value) is not None
        or any(
            unicodedata.category(character) in UNSAFE_CATEGORIES for character in title
        )
    )


def check_title(title: object, identifier: str) -> None:
    """Require one bounded, normalized, public-safe paper title."""
    check(
        isinstance(title, str)
        and bool(title)
        and title == " ".join(title.split())
        and len(title) <= MAX_TITLE,
        f"Support paper has an invalid title: {identifier}",
    )
    check(not unsafe_title(title), f"Support paper has an unsafe title: {identifier}")


def base_id(value: object) -> str:
    """Return a lowercase, version-free arXiv identifier."""
    check(isinstance(value, str), "Support paper has no arXiv ID")
    identifier = value.strip()
    if identifier.startswith("arxiv:"):
        identifier = identifier.removeprefix("arxiv:")
    elif identifier.startswith("https://arxiv.org/abs/"):
        identifier = identifier.removeprefix("https://arxiv.org/abs/")
    elif identifier.startswith("https://arxiv.org/pdf/"):
        identifier = identifier.removeprefix("https://arxiv.org/pdf/").removesuffix(
            ".pdf"
        )
    identifier = re.sub(r"v\d+$", "", identifier, flags=re.IGNORECASE).lower()
    check(
        bool(MODERN_ID.fullmatch(identifier) or LEGACY_ID.fullmatch(identifier)),
        f"Invalid support-paper arXiv ID: {value}",
    )
    return identifier


def published_month(value: object) -> str:
    """Return a validated publication month from an ISO timestamp."""
    check(isinstance(value, str), "Support paper has no publication timestamp")
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError as error:
        raise RuntimeError(
            "Support paper has an invalid publication timestamp"
        ) from error
    return parsed.strftime("%Y-%m")


def make_row(paper: dict, shard: dict, row: int) -> dict:
    """Project one archive paper into its minimal public support record."""
    identifier = base_id(paper.get("id") or paper.get("canonical_id"))
    raw_title = paper.get("title")
    check(isinstance(raw_title, str), f"Support paper has no title: {identifier}")
    title = " ".join(raw_title.split())
    check_title(title, identifier)
    published = paper.get("published")
    month = published_month(published)
    check(
        isinstance(row, int) and not isinstance(row, bool) and row >= 0,
        f"Support paper has an invalid archive row: {identifier}",
    )
    reference = {
        "month": shard.get("month"),
        "path": shard.get("path"),
        "sha256": shard.get("sha256"),
        "row": row,
    }
    check(
        reference["month"] == month,
        f"Support paper archive month drifted: {identifier}",
    )
    return {
        "canonical_id": f"arxiv:{identifier}",
        "title": title,
        "url": f"https://arxiv.org/abs/{identifier}",
        "published": published,
        "archive": reference,
    }


def check_ref(reference: object, identifier: str, month: str) -> None:
    """Validate one bounded monthly archive row reference."""
    check(
        isinstance(reference, dict) and set(reference) == ARCHIVE_FIELDS,
        f"Support paper has an invalid archive reference: {identifier}",
    )
    shard_month = reference.get("month")
    check(
        isinstance(shard_month, str)
        and bool(MONTH.fullmatch(shard_month))
        and shard_month == month,
        f"Support paper archive month drifted: {identifier}",
    )
    check(
        reference.get("path") == f"{shard_month}.json.gz",
        f"Support paper archive path drifted: {identifier}",
    )
    check(
        isinstance(reference.get("sha256"), str)
        and bool(SHA256.fullmatch(reference["sha256"])),
        f"Support paper has an invalid archive digest: {identifier}",
    )
    row = reference.get("row")
    check(
        isinstance(row, int) and not isinstance(row, bool) and row >= 0,
        f"Support paper has an invalid archive row: {identifier}",
    )


def check_paper(paper: object) -> None:
    """Validate one minimal public support-paper record."""
    check(
        isinstance(paper, dict) and set(paper) == PAPER_FIELDS,
        "Support paper has an unexpected shape",
    )
    canonical = paper.get("canonical_id")
    identifier = base_id(canonical)
    check(
        canonical == f"arxiv:{identifier}",
        f"Support paper ID is not canonical: {canonical}",
    )
    check_title(paper.get("title"), identifier)
    check(
        paper.get("url") == f"https://arxiv.org/abs/{identifier}",
        f"Support paper has an invalid public URL: {identifier}",
    )
    month = published_month(paper.get("published"))
    check_ref(paper.get("archive"), identifier, month)


def check_archive(bundle: dict, root: Path) -> None:
    """Resolve every reference against its exact content-addressed archive row."""
    shards: dict[str, tuple[str, dict]] = {}
    for paper in bundle["papers"]:
        reference = paper["archive"]
        path = root / reference["path"]
        check(path.is_file(), f"Support archive shard is missing: {reference['path']}")
        cached = shards.get(reference["path"])
        if cached is None:
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            check(
                digest == reference["sha256"],
                f"Support archive digest drifted: {path.name}",
            )
            cached = (digest, read_shard(path))
            shards[reference["path"]] = cached
        digest, shard = cached
        check(
            digest == reference["sha256"],
            f"Support archive digest drifted: {path.name}",
        )
        row = reference["row"]
        check(
            row < len(shard["papers"]),
            f"Support archive row is missing: {paper['canonical_id']}",
        )
        source = shard["papers"][row]
        expected = make_row(source, reference, row)
        check(
            expected == paper, f"Support archive row drifted: {paper['canonical_id']}"
        )


def validate_bundle(
    bundle: object,
    *,
    expected_digest: str | None = None,
    archive_root: Path | None = None,
) -> dict:
    """Validate bundle shape, lineage, ordering, digests, and optional source rows."""
    check(
        isinstance(bundle, dict) and set(bundle) == ROOT_FIELDS,
        "Support bundle has an unexpected shape",
    )
    check(bundle.get("schema_version") == SCHEMA_VERSION, "Unsupported support schema")
    source_digest = bundle.get("corpus_digest")
    check(
        isinstance(source_digest, str) and bool(SHA256.fullmatch(source_digest)),
        "Support bundle has an invalid corpus digest",
    )
    if expected_digest is not None:
        check(source_digest == expected_digest, "Support corpus generation drifted")
    papers = bundle.get("papers")
    check(isinstance(papers, list), "Support bundle has no paper list")
    for paper in papers:
        check_paper(paper)
    identifiers = [paper["canonical_id"] for paper in papers]
    check(
        identifiers == sorted(set(identifiers)),
        "Support papers are duplicated or unsorted",
    )
    references = [
        (paper["archive"]["path"], paper["archive"]["row"]) for paper in papers
    ]
    check(
        len(references) == len(set(references)), "Support archive rows are duplicated"
    )
    digest = bundle.get("content_sha256")
    check(
        isinstance(digest, str)
        and bool(SHA256.fullmatch(digest))
        and digest == content_digest(bundle),
        "Support bundle content digest drifted",
    )
    if archive_root is not None:
        check_archive(bundle, archive_root)
    return bundle


def build_bundle(rows: list[dict], source_digest: str) -> dict:
    """Build one sorted, content-addressed support-paper bundle."""
    check(
        isinstance(source_digest, str) and bool(SHA256.fullmatch(source_digest)),
        "Support bundle has an invalid corpus digest",
    )
    papers = sorted(rows, key=lambda paper: paper.get("canonical_id", ""))
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "corpus_digest": source_digest,
        "papers": papers,
    }
    bundle["content_sha256"] = content_digest(bundle)
    return validate_bundle(bundle)


def bundle_bytes(bundle: dict) -> bytes:
    """Return canonical publication bytes for one validated bundle."""
    validate_bundle(bundle)
    return json_bytes(bundle) + b"\n"
