import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from cloudaudit import MAGIC
from pack import (
    PACK_MAGIC,
    check_bytes,
    check_packs,
    pack_groups,
    pack_key,
    write_packs,
)


def month_at(index: int) -> str:
    """Return one month after the authenticated corpus epoch."""
    ordinal = 1986 * 12 + 3 + index
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"


def point_content(values: list[tuple[float, float, float, int]]) -> bytes:
    """Encode one monthly legacy point fixture."""
    positions = b"".join(struct.pack("<fff", *value[:3]) for value in values)
    scopes = bytes(value[3] for value in values)
    return struct.pack("<8sI", MAGIC, len(values)) + positions + scopes


def point_row(root: Path, month: str, values: list[tuple]) -> dict:
    """Write and describe one monthly point fixture."""
    content = point_content(values)
    path = root / f"{month}.bin"
    path.write_bytes(content)
    counts = {
        "likely": sum(value[3] == 0 for value in values),
        "possible": sum(value[3] == 1 for value in values),
        "outside": sum(value[3] == 2 for value in values),
    }
    return {
        "month": month,
        "count": len(values),
        "counts": counts,
        "points": {
            "path": path.name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        },
    }


class PackTests(unittest.TestCase):
    def test_corpus_epoch(self) -> None:
        self.assertEqual(pack_key("1986-04"), 0)
        self.assertEqual(pack_key("1987-05"), 0)
        self.assertEqual(pack_key("1987-06"), 1)
        self.assertEqual(pack_key("1991-08"), 4)
        with self.assertRaisesRegex(ValueError, "corpus epoch"):
            pack_key("1986-03")

    def test_fixed_groups(self) -> None:
        rows = [{"month": month_at(index)} for index in range(421)]
        groups = pack_groups(rows)

        self.assertEqual(len(groups), 31)
        self.assertTrue(all(1 <= len(group) <= 14 for _, group in groups))
        self.assertEqual(
            [row["month"] for _, group in groups for row in group],
            [row["month"] for row in rows],
        )

    def test_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                point_row(root, month_at(0), [(1.0, 2.0, 3.0, 0)]),
                point_row(
                    root,
                    month_at(1),
                    [(4.0, 5.0, 6.0, 1), (7.0, 8.0, 9.0, 2)],
                ),
            ]

            packs = write_packs(root, rows)
            content = (root / packs[0]["points"]["path"]).read_bytes()

            self.assertEqual(len(content), 12 + 3 * 13)
            self.assertEqual(struct.unpack("<8sI", content[:12]), (PACK_MAGIC, 3))
            self.assertEqual(content[-3:], bytes([0, 1, 2]))
            check_packs(root, rows, packs)

    def test_append_stability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                point_row(root, month_at(index), [(float(index), 0.0, 0.0, 0)])
                for index in range(14)
            ]
            first = write_packs(root, rows)[0]
            rows.append(point_row(root, month_at(14), [(14.0, 0.0, 0.0, 0)]))

            packs = write_packs(root, rows)

            self.assertEqual(packs[0], first)
            self.assertEqual(
                [pack["points"]["path"] for pack in packs], ["p000.bin", "p001.bin"]
            )

    def test_row_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                point_row(root, month_at(0), [(1.0, 0.0, 0.0, 0)]),
                point_row(root, month_at(1), [(2.0, 0.0, 0.0, 0)]),
            ]
            packs = write_packs(root, rows)
            first = root / rows[0]["points"]["path"]
            changed = point_content([(9.0, 0.0, 0.0, 0)])
            first.write_bytes(changed)
            rows[0]["points"] = {
                "path": first.name,
                "sha256": hashlib.sha256(changed).hexdigest(),
                "bytes": len(changed),
            }

            with self.assertRaisesRegex(RuntimeError, "rows drifted"):
                check_packs(root, rows, packs)

    def test_corrupt_bytes(self) -> None:
        content = bytearray(struct.pack("<8sIfffB", PACK_MAGIC, 1, 1.0, 2.0, 3.0, 0))
        struct.pack_into("<f", content, 12, float("nan"))
        with self.assertRaisesRegex(RuntimeError, "contract drifted"):
            check_bytes(bytes(content), 1, {"likely": 1, "possible": 0, "outside": 0})

        struct.pack_into("<f", content, 12, 1.0)
        content[-1] = 3
        with self.assertRaisesRegex(RuntimeError, "contract drifted"):
            check_bytes(bytes(content), 1, {"likely": 1, "possible": 0, "outside": 0})


if __name__ == "__main__":
    unittest.main()
