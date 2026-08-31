"""Read and write durable corpus bundles."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


PACK_LEVEL = 1
COPY_SIZE = 1024 * 1024


def pack_tree(root: Path, archive: Path) -> None:
    """Package a tree as a fast compatible gzip tarball."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix="corpus-", suffix=".tar.gz", dir=archive.parent
    )
    os.close(handle)
    temporary = Path(name)
    try:
        with tarfile.open(temporary, "w:gz", compresslevel=PACK_LEVEL) as bundle:
            for path in sorted(root.rglob("*")):
                bundle.add(path, arcname=path.relative_to(root), recursive=False)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def safe_member(member: tarfile.TarInfo) -> PurePosixPath:
    """Validate one bundle member and return its relative path."""
    path = PurePosixPath(member.name)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or not (member.isdir() or member.isreg())
        or member.size < 0
    ):
        raise ValueError("Corpus checkpoint contains an unsafe member")
    return path


def unpack_tree(archive: Path, root: Path, max_files: int, max_bytes: int) -> None:
    """Restore a validated gzip tarball in one streaming pass."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("Corpus restore directory is not empty")
    root.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix="corpus-", dir=root.parent))
    count = 0
    size = 0
    names: set[PurePosixPath] = set()
    try:
        with tarfile.open(archive, "r|gz") as bundle:
            for member in bundle:
                path = safe_member(member)
                count += 1
                size += member.size
                if count > max_files or size > max_bytes:
                    raise ValueError("Corpus checkpoint exceeds safe restore bounds")
                if path in names:
                    raise ValueError("Corpus checkpoint contains a duplicate member")
                names.add(path)
                target = staged.joinpath(*path.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError("Corpus checkpoint member could not be read")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=COPY_SIZE)
        os.replace(staged, root)
    finally:
        shutil.rmtree(staged, ignore_errors=True)
