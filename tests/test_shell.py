from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def legacy_shell() -> str:
    """Extract the legacy-normalization shell exactly as Actions runs it."""
    workflow = (ROOT / ".github/workflows/cloud.yml").read_text(encoding="utf-8")
    section = workflow.split("- name: Normalize legacy corpus shards", 1)[1]
    source = section.split("\n      - name:", 1)[0].split("run: |", 1)[1]
    return textwrap.dedent(source)


class ShellTests(unittest.TestCase):
    def test_legacy_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "runner"
            archive = root / "data/cache/archive"
            tools = root / "bin"
            runner.mkdir()
            archive.mkdir(parents=True)
            tools.mkdir()
            (runner / "cloud-needed.tsv").write_text("required\n", encoding="utf-8")
            (archive / "index.json").write_text(
                json.dumps({"schema_version": 1, "shards": []}),
                encoding="utf-8",
            )
            (root / "pipeline").symlink_to(ROOT / "pipeline", target_is_directory=True)
            jq = tools / "jq"
            jq.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            jq.chmod(0o755)
            (tools / "python").symlink_to(sys.executable)
            env = {
                **os.environ,
                "RUNNER_TEMP": str(runner),
                "ARCHIVE_ROOT": "data/cache/archive",
                "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
            }

            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", legacy_shell()],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((archive / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["all"], 0)


if __name__ == "__main__":
    unittest.main()
