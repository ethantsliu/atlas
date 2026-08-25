from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from files import atomic_copy, atomic_write_text  # noqa: E402


class AtomicIoTests(unittest.TestCase):
    def test_atomic_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            destination = root / "destination.json"
            atomic_write_text(source, '{"ok": true}\n')
            atomic_copy(source, destination)
            self.assertEqual(source.read_bytes(), destination.read_bytes())
            self.assertFalse(list(root.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
