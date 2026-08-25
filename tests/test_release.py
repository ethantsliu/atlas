import argparse
from pathlib import Path
import subprocess
import tempfile
import unittest

from pipeline import release


NAME = "Atlas Release"
EMAIL = "atlas-release@users.noreply.github.com"
ROOT = Path(__file__).resolve().parents[1]


def run_git(root: Path, *args: str, input_data: bytes | None = None) -> str:
    """Run Git only inside an isolated test repository."""
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        input=input_data,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode().strip()


def make_repo(base: Path, content: bytes = b"public\n") -> tuple[Path, Path]:
    """Create a one-root-commit candidate and an external deny file."""
    root = base / "candidate"
    root.mkdir()
    run_git(root, "init", "--initial-branch=main")
    run_git(root, "config", "user.name", NAME)
    run_git(root, "config", "user.email", EMAIL)
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/check.yml").write_text("name: check\n")
    (root / "README.md").write_bytes(content)
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "Public root")
    deny = base / "privacy-patterns.txt"
    deny.write_text("private-example-value\n")
    return root, deny


def arguments(root: Path, deny: Path) -> argparse.Namespace:
    """Build staging-mode verifier arguments."""
    return argparse.Namespace(
        repo=root,
        identity_name=NAME,
        identity_email=EMAIL,
        deny_file=deny,
        origin=None,
        expected_head=None,
    )


class ReleaseTests(unittest.TestCase):
    def test_clean_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, deny = make_repo(Path(directory))
            checks = release.verify(arguments(root, deny))
        self.assertTrue(checks)
        self.assertTrue(all(check.passed for check in checks), checks)

    def test_private_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private_path = b"path=/" + b"Users/alice/work/atlas\n"
            root, deny = make_repo(Path(directory), private_path)
            checks = release.verify(arguments(root, deny))
        privacy = next(check for check in checks if check.name == "privacy scan")
        self.assertFalse(privacy.passed)
        self.assertIn("README.md (unix home path)", privacy.detail)
        self.assertNotIn("alice", privacy.detail)
        self.assertNotIn("and -", privacy.detail)

    def test_extra_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, deny = make_repo(Path(directory))
            run_git(
                root, "hash-object", "-w", "--stdin", input_data=b"old private object\n"
            )
            checks = release.verify(arguments(root, deny))
        objects = next(check for check in checks if check.name == "fresh object DB")
        fsck = next(check for check in checks if check.name == "strict fsck")
        self.assertFalse(objects.passed)
        self.assertFalse(fsck.passed)

    def test_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, deny = make_repo(Path(directory))
            args = arguments(root, deny)
            args.identity_email = "other@users.noreply.github.com"
            checks = release.verify(args)
        identity = next(check for check in checks if check.name == "commit identity")
        self.assertFalse(identity.passed)

    def test_external_deny(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _ = make_repo(Path(directory))
            inside = root / "privacy-patterns.txt"
            inside.write_text("private-example-value\n")
            checks = release.verify(arguments(root, inside))
        self.assertEqual(checks[0].name, "arguments")
        self.assertFalse(checks[0].passed)

    def test_path_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, deny = make_repo(Path(directory))
            private = root / "private-example-value.txt"
            private.write_text("not sensitive\n")
            run_git(root, "add", private.name)
            run_git(root, "commit", "--amend", "--no-edit")
            checks = release.verify(arguments(root, deny))
        privacy = next(check for check in checks if check.name == "privacy scan")
        self.assertFalse(privacy.passed)
        self.assertIn("<private path>", privacy.detail)
        self.assertNotIn("private-example-value", privacy.detail)

    def test_origin_validation(self) -> None:
        self.assertTrue(release.valid_origin("https://github.com/example/atlas.git"))
        self.assertFalse(release.valid_origin("git@github.com:example/atlas.git"))
        self.assertFalse(
            release.valid_origin("https://token@github.com/example/atlas.git")
        )
        self.assertFalse(release.valid_origin("file:///tmp/atlas"))

    def test_scanner_source(self) -> None:
        for path in (
            ROOT / "pipeline/release.py",
            ROOT / "tests/test_release.py",
            ROOT / "docs/RELEASE.md",
        ):
            content = path.read_bytes()
            for name, pattern in release.BUILTINS:
                self.assertIsNone(pattern.search(content), f"{path}: {name}")

    def test_anonymous_clone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, deny = make_repo(Path(directory))
            origin = "https://github.com/example/atlas.git"
            head = run_git(root, "rev-parse", "HEAD")
            run_git(root, "remote", "add", "origin", origin)
            run_git(root, "update-ref", "refs/remotes/origin/main", head)
            run_git(
                root,
                "symbolic-ref",
                "refs/remotes/origin/HEAD",
                "refs/remotes/origin/main",
            )
            args = arguments(root, deny)
            args.origin = origin
            args.expected_head = head
            checks = release.verify(args)
        self.assertTrue(all(check.passed for check in checks), checks)


if __name__ == "__main__":
    unittest.main()
