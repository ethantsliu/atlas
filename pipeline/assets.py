"""Publish full-reading records as deterministic static detail assets."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from files import atomic_write_bytes
from privacy import validate_public
from titles import valid_title

PUBLIC_READING_PREFIX = "/data/readings/"
PUBLIC_PAPER_PREFIX = "/data/papers/"
_SLUG_LIMIT = 72
_PUBLIC_READING_PATH = re.compile(
    r"^/data/readings/[a-z0-9][a-z0-9-]{0,71}--[0-9a-f]{12}-[0-9a-f]{12}\.json$"
)
_PUBLIC_PAPER_PATH = re.compile(r"^/data/papers/[0-9a-f]{64}\.json$")


class ReadingAssetError(RuntimeError):
    """Raised when the source-to-public reading contract is inconsistent."""


class PaperAssetError(RuntimeError):
    """Raised when a public paper bundle fails its byte contract."""


def validate_output(output_dir: Path, trust_root: Path) -> None:
    """Reject paper output paths that escape or traverse their public root."""
    root = trust_root.absolute()
    output = output_dir.absolute()
    if trust_root.is_symlink() or not trust_root.is_dir():
        raise PaperAssetError(f"Paper asset root must be a regular directory: {root}")
    try:
        output.relative_to(root)
    except ValueError as error:
        raise PaperAssetError("Paper asset output escapes its public root") from error
    for component in (output, *output.parents):
        if component == root:
            break
        if component.is_symlink():
            raise PaperAssetError(
                f"Paper asset output cannot traverse a symlink: {component}"
            )
    resolved_root = trust_root.resolve(strict=True)
    resolved_output = output_dir.resolve(strict=False)
    if (
        resolved_root != resolved_output
        and resolved_root not in resolved_output.parents
    ):
        raise PaperAssetError("Paper asset output resolves outside its public root")
    if output_dir.exists() and (output_dir.is_symlink() or not output_dir.is_dir()):
        raise PaperAssetError("Paper asset output must be a regular directory")


def paper_bytes(bundle: dict) -> bytes:
    """Serialize a paper bundle canonically for hashing and publication."""
    if not isinstance(bundle, dict) or not isinstance(bundle.get("papers"), list):
        raise PaperAssetError("Paper bundle must contain a paper list")
    if any(not valid_title(paper.get("title")) for paper in bundle["papers"]):
        raise PaperAssetError("Paper bundle contains an unsafe title")
    return (
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def paper_asset(bundle: dict) -> tuple[dict, bytes]:
    """Derive immutable public metadata and canonical bytes for a paper bundle."""
    content = paper_bytes(bundle)
    digest = hashlib.sha256(content).hexdigest()
    return (
        {
            "schema_version": 1,
            "path": f"{PUBLIC_PAPER_PREFIX}{digest}.json",
            "sha256": digest,
            "bytes": len(content),
            "paper_count": len(bundle["papers"]),
        },
        content,
    )


def paper_valid(path: Path) -> bool:
    """Return whether a regular asset's filename matches its exact digest."""
    return bool(
        path.is_file()
        and re.fullmatch(r"[0-9a-f]{64}\.json", path.name)
        and hashlib.sha256(path.read_bytes()).hexdigest() == path.stem
    )


def paper_safe(path: Path) -> bool:
    """Return whether a valid bundle satisfies the public paper-only boundary."""
    if not paper_valid(path):
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        validate_public(value, f"Paper asset {path.name}")
        papers = value.get("papers")
        if not isinstance(papers, list) or any(
            not isinstance(paper, dict)
            or paper.get("record_kind") == "non_paper_context"
            or {"note", "section", "tags"}.intersection(paper)
            or not valid_title(paper.get("title"))
            for paper in papers
        ):
            return False
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError):
        return False
    return True


def stage_papers(
    output_dir: Path,
    bundle: dict,
    trust_root: Path | None = None,
) -> dict:
    """Publish a content-addressed paper bundle before its core index."""
    validate_output(output_dir, trust_root or output_dir.parent)
    metadata, content = paper_asset(bundle)
    output_dir.mkdir(parents=True, exist_ok=True)
    validate_output(output_dir, trust_root or output_dir.parent)
    path = output_dir / Path(metadata["path"]).name
    atomic_write_bytes(path, content)
    if path.read_bytes() != content:
        raise PaperAssetError("Published paper bundle bytes changed after staging")
    return metadata


def current_asset(output_dir: Path, metadata: dict) -> Path:
    """Resolve and verify the bundle named by current public metadata."""
    path = metadata.get("path")
    if not isinstance(path, str) or not _PUBLIC_PAPER_PATH.fullmatch(path):
        raise PaperAssetError("Paper asset path is invalid")
    current = output_dir / Path(path).name
    if not current.is_file():
        raise PaperAssetError("Current paper bundle is missing before pruning")
    content = current.read_bytes()
    if len(content) != metadata.get("bytes") or hashlib.sha256(
        content
    ).hexdigest() != metadata.get("sha256"):
        raise PaperAssetError("Current paper bundle fails its byte contract")
    return current


def asset_files(output_dir: Path) -> list[Path]:
    """Return regular paper assets after rejecting unsafe directory entries."""
    files = list(output_dir.iterdir())
    for existing in files:
        if existing.is_symlink() or not existing.is_file():
            raise PaperAssetError(
                f"Paper asset output contains a non-regular file: {existing}"
            )
    return files


def retained_assets(
    files: list[Path], current: Path, prior_path: str | None
) -> set[Path]:
    """Choose current plus the exact or newest valid predecessor."""
    retained = {current}
    if prior_path is not None:
        if not _PUBLIC_PAPER_PATH.fullmatch(prior_path):
            raise PaperAssetError("Prior paper asset path is invalid")
        prior = current.parent / Path(prior_path).name
        if prior.is_file():
            if not paper_valid(prior):
                raise PaperAssetError("Prior paper asset digest is invalid")
            if paper_safe(prior):
                retained.add(prior)
    if len(retained) == 1:
        candidates = sorted(
            (path for path in files if path != current),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for candidate in candidates:
            if paper_safe(candidate):
                retained.add(candidate)
                break
    return retained


def prune_papers(
    output_dir: Path,
    metadata: dict,
    prior_path: str | None = None,
    trust_root: Path | None = None,
) -> None:
    """Retain current and prior bundles after the new core becomes public."""
    validate_output(output_dir, trust_root or output_dir.parent)
    current = current_asset(output_dir, metadata)
    files = asset_files(output_dir)
    retained = retained_assets(files, current, prior_path)
    for existing in files:
        if existing not in retained and (existing.is_file() or existing.is_symlink()):
            existing.unlink()


def validate_papers(
    output_dir: Path,
    metadata: dict,
    bundle: dict,
    trust_root: Path | None = None,
) -> None:
    """Require one exact content-addressed bundle and matching metadata."""
    validate_output(output_dir, trust_root or output_dir.parent)
    expected, content = paper_asset(bundle)
    if metadata != expected:
        raise PaperAssetError("Paper asset metadata is stale")
    expected_name = Path(expected["path"]).name
    actual_names = (
        {entry.name for entry in output_dir.iterdir()} if output_dir.exists() else set()
    )
    if expected_name not in actual_names or len(actual_names) > 2:
        raise PaperAssetError("Published paper asset set is stale")
    if (output_dir / expected_name).read_bytes() != content:
        raise PaperAssetError("Published paper bundle bytes are stale")
    for name in actual_names - {expected_name}:
        if not re.fullmatch(r"[0-9a-f]{64}\.json", name):
            raise PaperAssetError("Retained paper asset name is invalid")
        retained = (output_dir / name).read_bytes()
        if hashlib.sha256(retained).hexdigest() != Path(name).stem:
            raise PaperAssetError("Retained paper asset digest is invalid")
        if not paper_safe(output_dir / name):
            raise PaperAssetError("Retained paper asset violates public privacy")


def _slug(value: str) -> str:
    """Return a readable ASCII label while leaving uniqueness to the digest."""
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-") or "reading"


def reading_content_digest(reading: dict) -> str:
    """Hash semantic content so a revised reading receives a new static URL."""
    if not isinstance(reading, dict):
        raise ReadingAssetError("Reading content must be an object")
    canonical = json.dumps(
        reading,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:12]


def reading_asset_filename(stable_id: str, reading: dict) -> str:
    """Map identity and content to a safe, collision-resistant filename."""
    if not isinstance(stable_id, str) or not stable_id.strip():
        raise ReadingAssetError("Reading stable ID must be a non-empty string")
    identity_digest = hashlib.sha256(stable_id.encode("utf-8")).hexdigest()[:12]
    return (
        f"{_slug(stable_id)[:_SLUG_LIMIT]}--{identity_digest}-"
        f"{reading_content_digest(reading)}.json"
    )


def reading_public_path(stable_id: str, reading: dict) -> str:
    """Return the root-relative path used by the static web application."""
    return f"{PUBLIC_READING_PREFIX}{reading_asset_filename(stable_id, reading)}"


def is_public_path(value: object) -> bool:
    """Return whether a browser path matches the content-addressed static contract."""
    return isinstance(value, str) and bool(_PUBLIC_READING_PATH.fullmatch(value))


def _symlink_component(path: Path, stop_at: Path) -> Path | None:
    """Return a symlink below the source/output lexical trust boundary."""
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component == stop_at:
            return None
        if component.is_symlink():
            return component
    return None


def validate_read_dir(source_dir: Path, output_dir: Path) -> None:
    """Reject resolved source/output overlap before any generated-file mutation."""
    if source_dir.is_symlink():
        raise ReadingAssetError(
            f"Reviewed reading source directory cannot be a symlink: {source_dir}"
        )
    absolute_source = source_dir.absolute()
    absolute_output = output_dir.absolute()
    source_ancestors = {absolute_source, *absolute_source.parents}
    common_ancestor = next(
        component
        for component in (absolute_output, *absolute_output.parents)
        if component in source_ancestors
    )
    output_symlink = _symlink_component(output_dir, common_ancestor)
    if output_symlink is not None:
        raise ReadingAssetError(
            f"Generated reading output path cannot traverse a symlink: {output_symlink}"
        )
    try:
        resolved_source = source_dir.resolve(strict=True)
    except OSError as error:
        raise ReadingAssetError(
            f"Cannot resolve reading source directory {source_dir}: {error}"
        ) from error
    if not resolved_source.is_dir():
        raise ReadingAssetError(f"Reading source is not a directory: {source_dir}")

    try:
        resolved_output = output_dir.resolve(strict=False)
    except OSError as error:
        raise ReadingAssetError(
            f"Cannot resolve reading output directory {output_dir}: {error}"
        ) from error
    directories_overlap = (
        resolved_source == resolved_output
        or resolved_source in resolved_output.parents
        or resolved_output in resolved_source.parents
    )
    if directories_overlap:
        raise ReadingAssetError(
            "Reviewed reading source and generated output directories overlap after "
            f"symlink resolution: {resolved_source} and {resolved_output}"
        )


def index_reading_sources(source_dir: Path) -> dict[str, Path]:
    """Index source files by semantic identity and reject duplicate IDs."""
    indexed: dict[str, Path] = {}
    for source in sorted(source_dir.glob("*.json")):
        if source.is_symlink() or not source.is_file():
            raise ReadingAssetError(
                f"Reading source must be a regular, non-symlink file: {source}"
            )
        try:
            reading = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReadingAssetError(
                f"Cannot parse reading source {source}: {error}"
            ) from error
        stable_id = reading.get("stable_id") if isinstance(reading, dict) else None
        if not isinstance(stable_id, str) or not stable_id:
            raise ReadingAssetError(f"Reading source lacks a stable ID: {source}")
        if stable_id in indexed:
            raise ReadingAssetError(
                f"Duplicate reading stable ID {stable_id}: {indexed[stable_id]} and {source}"
            )
        indexed[stable_id] = source
    return indexed


def index_asset_names(readings: dict[str, dict]) -> dict[str, str]:
    """Derive every output name and reject a collision before publication."""
    names = {
        stable_id: reading_asset_filename(stable_id, reading)
        for stable_id, reading in readings.items()
    }
    if len(set(names.values())) != len(names):
        raise ReadingAssetError("Derived reading asset filenames collide")
    return names


def stage_reading_assets(source_dir: Path, output_dir: Path) -> dict[str, str]:
    """Publish current detail bytes while retaining assets used by an older index."""
    validate_read_dir(source_dir, output_dir)
    sources = index_reading_sources(source_dir)
    source_bytes = {
        stable_id: source.read_bytes() for stable_id, source in sources.items()
    }
    source_readings = {
        stable_id: json.loads(content.decode("utf-8"))
        for stable_id, content in source_bytes.items()
    }
    asset_names = index_asset_names(source_readings)
    output_dir.mkdir(parents=True, exist_ok=True)
    validate_read_dir(source_dir, output_dir)

    for stable_id, content in source_bytes.items():
        atomic_write_bytes(output_dir / asset_names[stable_id], content)

    return {
        stable_id: reading_public_path(stable_id, source_readings[stable_id])
        for stable_id in sources
    }


def prune_reading_assets(
    source_dir: Path,
    output_dir: Path,
    staged_paths: dict[str, str],
) -> None:
    """Remove old detail versions only after their replacement index is public."""
    validate_read_dir(source_dir, output_dir)
    sources = index_reading_sources(source_dir)
    source_readings = {
        stable_id: json.loads(source.read_text(encoding="utf-8"))
        for stable_id, source in sources.items()
    }
    current_paths = {
        stable_id: reading_public_path(stable_id, source_readings[stable_id])
        for stable_id in sources
    }
    if staged_paths != current_paths:
        raise ReadingAssetError("Reading sources changed after detail staging")

    expected_names = {Path(path).name for path in staged_paths.values()}
    for stable_id, source in sources.items():
        staged = output_dir / Path(staged_paths[stable_id]).name
        if not staged.is_file() or staged.read_bytes() != source.read_bytes():
            raise ReadingAssetError(
                f"Staged reading bytes changed before pruning: {stable_id}"
            )
    for existing in output_dir.iterdir():
        if existing.name not in expected_names and (
            existing.is_file() or existing.is_symlink()
        ):
            existing.unlink()


def publish_reading_assets(source_dir: Path, output_dir: Path) -> dict[str, str]:
    """Publish and immediately prune an isolated detail destination."""
    staged_paths = stage_reading_assets(source_dir, output_dir)
    prune_reading_assets(source_dir, output_dir, staged_paths)
    return staged_paths


def validate_reading_assets(
    source_dir: Path,
    output_dir: Path,
    readings: dict[str, dict],
) -> None:
    """Require exact IDs, filenames, bytes, and parsed semantics across a copy."""
    validate_read_dir(source_dir, output_dir)
    sources = index_reading_sources(source_dir)
    if set(sources) != set(readings):
        raise ReadingAssetError("Loaded readings and source reading files disagree")

    asset_names = index_asset_names(readings)
    expected_names = set(asset_names.values())
    actual_names = (
        {entry.name for entry in output_dir.iterdir()} if output_dir.exists() else set()
    )
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        stale = sorted(actual_names - expected_names)
        raise ReadingAssetError(
            f"Published reading assets disagree (missing={missing}, stale={stale})"
        )

    for stable_id, source in sources.items():
        published = output_dir / asset_names[stable_id]
        if not published.is_file() or source.read_bytes() != published.read_bytes():
            raise ReadingAssetError(f"Published reading bytes are stale: {stable_id}")
        try:
            parsed = json.loads(published.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReadingAssetError(
                f"Cannot parse published reading {published}: {error}"
            ) from error
        if parsed != readings[stable_id]:
            raise ReadingAssetError(
                f"Published reading semantics are stale: {stable_id}"
            )
