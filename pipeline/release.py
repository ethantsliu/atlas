"""Read-only verification for a clean public release repository."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


NOREPLY = re.compile(r"^[^@\s]+@users\.noreply\.github\.com$", re.IGNORECASE)
OBJECT = re.compile(r"^[0-9a-f]{40,64}$")
BUILTINS = (
    ("unix home path", re.compile(rb"/(?:users|home)/[^/\\\x00\s]+[/\\]", re.I)),
    (
        "root home path",
        re.compile(rb"(?<![a-z0-9])/" + rb"root(?:[/\\]|\b)", re.I),
    ),
    (
        "Windows home path",
        re.compile(rb"[a-z]:[/\\]+users[/\\]+[^/\\\x00\s]+[/\\]", re.I),
    ),
    (
        "personal social URL",
        re.compile(
            rb"https?://(?:mobile\.)?(?:twitter\.com|x\.com)/[a-z0-9_]+",
            re.I,
        ),
    ),
    (
        "internal reviewer identity",
        re.compile(
            rb'"reviewer_id"\s*:\s*"(?!reviewer-[0-9a-f]{12}")'
            rb'[^"\r\n]*(?:codex|agent|reader|secondary|root|local|visual|fleet)'
            rb'[^"\r\n]*"',
            re.I,
        ),
    ),
)
GIT_PREFIX = (
    "git",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "maintenance.auto=0",
    "-c",
    "gc.auto=0",
)


@dataclass(frozen=True)
class Check:
    """One release-verification result."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Pattern:
    """A privacy pattern whose matching text must never be printed."""

    name: str
    regex: re.Pattern[bytes]


def git_env() -> dict[str, str]:
    """Return an environment which disables prompts and optional Git writes."""
    env = os.environ.copy()
    env.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return env


def git_run(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run one bounded, non-networking Git inspection command."""
    return subprocess.run(
        (*GIT_PREFIX, "-C", str(root), *args),
        check=False,
        capture_output=True,
        env=git_env(),
        timeout=120,
    )


def git_text(root: Path, *args: str) -> tuple[int, str, str]:
    """Run Git and decode its stable diagnostic streams."""
    result = git_run(root, *args)
    return (
        result.returncode,
        result.stdout.decode("utf-8", "replace").strip(),
        result.stderr.decode("utf-8", "replace").strip(),
    )


def add_check(checks: list[Check], name: str, passed: bool, detail: str) -> None:
    """Append a normalized result without exposing matched private text."""
    checks.append(Check(name, passed, detail))


def load_patterns(path: Path, root: Path) -> tuple[Pattern, ...]:
    """Load case-insensitive literal deny entries kept outside the candidate."""
    resolved = path.expanduser().resolve(strict=True)
    if resolved == root or root in resolved.parents:
        raise ValueError("privacy deny file must be outside the candidate repository")
    patterns: list[Pattern] = []
    for number, raw in enumerate(resolved.read_bytes().splitlines(), start=1):
        value = raw.strip()
        if not value or value.startswith(b"#"):
            continue
        if len(value) < 4:
            raise ValueError(f"privacy deny entry {number} is shorter than 4 bytes")
        patterns.append(
            Pattern(
                f"private literal line {number}", re.compile(re.escape(value), re.I)
            )
        )
    if not patterns:
        raise ValueError("privacy deny file has no active literal entries")
    return tuple(patterns)


def check_layout(root: Path, checks: list[Check]) -> bool:
    """Require an ordinary, self-contained Git working repository."""
    dotgit = root / ".git"
    ordinary = dotgit.is_dir() and not dotgit.is_symlink()
    add_check(checks, "ordinary Git directory", ordinary, ".git is a local directory")
    if not ordinary:
        return False
    code, top, _ = git_text(root, "rev-parse", "--show-toplevel")
    same_root = code == 0 and Path(top).resolve() == root
    add_check(
        checks, "repository root", same_root, "requested path is the worktree root"
    )
    code, common, _ = git_text(root, "rev-parse", "--git-common-dir")
    common_path = (root / common).resolve() if code == 0 else Path()
    isolated = code == 0 and common_path == dotgit.resolve()
    add_check(
        checks, "private object DB", isolated, "no linked-worktree object database"
    )
    alternates = dotgit / "objects/info/alternates"
    grafts = dotgit / "info/grafts"
    no_links = not (alternates.exists() and alternates.read_bytes().strip())
    no_grafts = not (grafts.exists() and grafts.read_bytes().strip())
    add_check(checks, "no alternates", no_links, "object store has no alternates")
    add_check(checks, "no grafts", no_grafts, "history has no graft overlay")
    code, shallow, _ = git_text(root, "rev-parse", "--is-shallow-repository")
    add_check(
        checks, "complete repository", code == 0 and shallow == "false", "not shallow"
    )
    code, partial, _ = git_text(
        root,
        "config",
        "--get-regexp",
        r"^(extensions\.partialClone|remote\..*\.promisor)$",
    )
    add_check(
        checks, "no partial clone", code == 1 and not partial, "no promisor config"
    )
    return same_root and isolated and no_links and no_grafts


def parse_refs(raw: str) -> list[tuple[str, str, str]]:
    """Parse tab-delimited ref name, object, and symbolic target triples."""
    refs: list[tuple[str, str, str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        fields = line.split("\t", 2)
        fields.extend("" for _ in range(3 - len(fields)))
        refs.append(tuple(fields))
    return refs


def check_refs(
    root: Path,
    checks: list[Check],
    origin: str | None,
    expected: str | None,
) -> str | None:
    """Verify HEAD, refs, remotes, and the single public root commit."""
    code, head, _ = git_text(root, "rev-parse", "--verify", "HEAD")
    valid_head = code == 0 and bool(OBJECT.fullmatch(head))
    add_check(
        checks, "valid HEAD", valid_head, head if valid_head else "HEAD is invalid"
    )
    if not valid_head:
        return None
    code, branch, _ = git_text(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    attached = code == 0 and branch == "main"
    add_check(
        checks,
        "attached main branch",
        attached,
        branch if attached else "HEAD is not attached to main",
    )
    code, raw, _ = git_text(
        root,
        "for-each-ref",
        "--format=%(refname)%09%(objectname)%09%(symref)",
    )
    refs = parse_refs(raw) if code == 0 else []
    local_ref = f"refs/heads/{branch}"
    allowed = {local_ref}
    required = {local_ref}
    if origin:
        remote_ref = f"refs/remotes/origin/{branch}"
        allowed.update(
            {
                remote_ref,
                "refs/remotes/origin/HEAD",
            }
        )
        required.add(remote_ref)
    names = {item[0] for item in refs}
    refs_valid = bool(refs) and all(
        name in allowed and oid == head for name, oid, _ in refs
    )
    refs_valid = refs_valid and required <= names
    refs_valid = refs_valid and all(
        name != "refs/remotes/origin/HEAD"
        or symbolic == f"refs/remotes/origin/{branch}"
        for name, _, symbolic in refs
    )
    add_check(checks, "single release ref", refs_valid, f"{len(refs)} allowed ref(s)")
    code, remotes, _ = git_text(root, "remote")
    remote_names = remotes.splitlines() if code == 0 and remotes else []
    expected_remotes = ["origin"] if origin else []
    add_check(
        checks,
        "release remotes",
        remote_names == expected_remotes,
        "only expected remotes are configured",
    )
    if origin:
        code, actual, _ = git_text(
            root,
            "config",
            "--file",
            ".git/config",
            "--get-all",
            "remote.origin.url",
        )
        add_check(
            checks,
            "anonymous origin",
            code == 0 and actual == origin,
            "origin URL matches",
        )
    code, count, _ = git_text(root, "rev-list", "--all", "--count")
    one_commit = code == 0 and count == "1"
    add_check(
        checks,
        "one commit",
        one_commit,
        f"reachable commit count: {count or 'unknown'}",
    )
    code, parents, _ = git_text(root, "rev-list", "--parents", "-n", "1", "HEAD")
    root_commit = code == 0 and len(parents.split()) == 1
    add_check(checks, "root commit", root_commit, "HEAD has no parents")
    if expected:
        add_check(
            checks,
            "expected public SHA",
            head == expected,
            "HEAD matches recorded staging SHA",
        )
    return head


def check_objects(root: Path, checks: list[Check], head: str) -> None:
    """Compare every stored object with objects reachable from the root commit."""
    code, stored, error = git_text(
        root,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname)",
    )
    stored_set = set(stored.splitlines()) if code == 0 else set()
    code2, reachable, error2 = git_text(
        root,
        "rev-list",
        "--objects",
        "--no-object-names",
        head,
    )
    reachable_set = set(reachable.splitlines()) if code2 == 0 else set()
    exact = code == code2 == 0 and stored_set == reachable_set and bool(stored_set)
    detail = f"{len(stored_set)} stored / {len(reachable_set)} reachable objects"
    if error or error2:
        detail = "object enumeration failed"
    add_check(checks, "fresh object DB", exact, detail)
    code, output, error = git_text(
        root,
        "fsck",
        "--full",
        "--strict",
        "--no-reflogs",
        "--unreachable",
        head,
    )
    findings = tuple(
        line for line in (output + "\n" + error).splitlines() if line.strip()
    )
    add_check(checks, "strict fsck", code == 0 and not findings, "no fsck findings")


def check_tree(root: Path, checks: list[Check]) -> list[tuple[str, str]]:
    """Require a clean, self-contained tree and return path/blob pairs."""
    code, status, _ = git_text(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=all",
    )
    add_check(
        checks, "clean worktree", code == 0 and not status, "index and files match HEAD"
    )
    result = git_run(root, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    entries: list[tuple[str, str]] = []
    gitlinks = False
    if result.returncode == 0:
        for record in result.stdout.split(b"\x00"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8", "surrogateescape")
            gitlinks = gitlinks or mode == "160000" or kind == "commit"
            if kind == "blob":
                entries.append((path, oid))
    add_check(
        checks,
        "no submodules",
        result.returncode == 0 and not gitlinks,
        "tree has no gitlinks",
    )
    paths = {path for path, _ in entries}
    add_check(
        checks,
        "CI workflow included",
        ".github/workflows/check.yml" in paths,
        "check workflow exists in HEAD",
    )
    return entries


def batch_blobs(root: Path, objects: list[str]) -> dict[str, bytes]:
    """Read committed blobs in one Git batch without checking out or filtering."""
    if not objects:
        return {}
    request = ("\n".join(objects) + "\n").encode("ascii")
    result = subprocess.run(
        (*GIT_PREFIX, "-C", str(root), "cat-file", "--batch"),
        input=request,
        check=False,
        capture_output=True,
        env=git_env(),
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError("git cat-file batch failed")
    blobs: dict[str, bytes] = {}
    cursor = 0
    for expected in objects:
        end = result.stdout.index(b"\n", cursor)
        oid, kind, size = result.stdout[cursor:end].decode("ascii").split()
        if oid != expected or kind != "blob":
            raise RuntimeError("unexpected object in git cat-file batch")
        cursor = end + 1
        length = int(size)
        blobs[oid] = result.stdout[cursor : cursor + length]
        cursor += length + 1
    return blobs


def privacy_scan(
    root: Path,
    checks: list[Check],
    entries: list[tuple[str, str]],
    private: tuple[Pattern, ...],
    head: str,
) -> None:
    """Scan committed paths, blobs, and commit metadata without echoing matches."""
    patterns = tuple(Pattern(name, regex) for name, regex in BUILTINS) + private
    objects = list(dict.fromkeys(oid for _, oid in entries))
    try:
        blobs = batch_blobs(root, objects)
    except (RuntimeError, ValueError) as error:
        add_check(checks, "privacy scan", False, str(error))
        return
    code, commit, _ = git_text(root, "cat-file", "commit", head)
    findings: set[tuple[str, str]] = set()
    for path, oid in entries:
        path_bytes = path.encode("utf-8", "surrogateescape")
        for pattern in patterns:
            if pattern.regex.search(path_bytes):
                findings.add(("<private path>", pattern.name))
            elif pattern.regex.search(blobs[oid]):
                findings.add((path, pattern.name))
    if code == 0:
        for pattern in patterns:
            if pattern.regex.search(commit.encode("utf-8", "surrogateescape")):
                findings.add(("<commit metadata>", pattern.name))
    detail = "no privacy matches"
    if findings:
        shown = sorted(findings)[:12]
        sample = ", ".join(f"{path} ({name})" for path, name in shown)
        remainder = len(findings) - len(shown)
        detail = sample + (f", and {remainder} more" if remainder else "")
    add_check(checks, "privacy scan", code == 0 and not findings, detail)


def check_identity(
    root: Path,
    checks: list[Check],
    name: str,
    email: str,
) -> None:
    """Require exact neutral author and committer identities on every commit."""
    expected_valid = bool(NOREPLY.fullmatch(email)) and bool(name.strip())
    add_check(
        checks,
        "noreply expectation",
        expected_valid,
        "expected identity is neutral/noreply",
    )
    code, raw, _ = git_text(
        root,
        "log",
        "--all",
        "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00",
    )
    fields = raw.split("\x00")
    if fields and not fields[-1]:
        fields.pop()
    records = [fields[index : index + 5] for index in range(0, len(fields), 5)]
    exact = (
        code == 0
        and bool(records)
        and all(
            len(record) == 5
            and record[1] == name
            and record[2].lower() == email.lower()
            and record[3] == name
            and record[4].lower() == email.lower()
            for record in records
        )
    )
    add_check(
        checks,
        "commit identity",
        expected_valid and exact,
        "author and committer match exactly",
    )


def valid_origin(value: str) -> bool:
    """Accept only credential-free public GitHub HTTPS repository URLs."""
    parsed = urlsplit(value)
    segments = [segment for segment in parsed.path.split("/") if segment]
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() == "github.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and len(segments) == 2
    )


def verify(args: argparse.Namespace) -> list[Check]:
    """Run every read-only release check which can be proven locally."""
    checks: list[Check] = []
    try:
        root = args.repo.expanduser().resolve(strict=True)
        private = load_patterns(args.deny_file, root)
    except OSError:
        return [Check("arguments", False, "repository or deny file is not readable")]
    except ValueError as error:
        return [Check("arguments", False, str(error))]
    if args.origin and not valid_origin(args.origin):
        return [
            Check(
                "arguments", False, "origin must be a credential-free GitHub HTTPS URL"
            )
        ]
    if bool(args.origin) != bool(args.expected_head):
        return [
            Check(
                "arguments", False, "origin and expected-head must be supplied together"
            )
        ]
    if args.expected_head and not OBJECT.fullmatch(args.expected_head):
        return [Check("arguments", False, "expected-head is not a full object ID")]
    if not check_layout(root, checks):
        return checks
    head = check_refs(root, checks, args.origin, args.expected_head)
    if not head:
        return checks
    check_objects(root, checks, head)
    entries = check_tree(root, checks)
    check_identity(root, checks, args.identity_name, args.identity_email)
    privacy_scan(root, checks, entries, private, head)
    return checks


def parser() -> argparse.ArgumentParser:
    """Build the command-line interface for staging and anonymous clones."""
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("repo", type=Path, help="candidate repository root")
    cli.add_argument("--identity-name", required=True, help="exact neutral commit name")
    cli.add_argument(
        "--identity-email", required=True, help="exact GitHub noreply email"
    )
    cli.add_argument(
        "--deny-file",
        required=True,
        type=Path,
        help="external file of case-insensitive private literals",
    )
    cli.add_argument("--origin", help="expected anonymous HTTPS origin URL")
    cli.add_argument(
        "--expected-head", help="full SHA recorded from the staging repository"
    )
    return cli


def main() -> int:
    """Print an auditable checklist and return nonzero on any failed proof."""
    checks = verify(parser().parse_args())
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
    failed = sum(not check.passed for check in checks)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    if failed:
        return 1
    print(
        "Local proof complete; remote visibility and hosted CI still require manual proof."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
