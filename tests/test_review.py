import copy
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from review import check_receipt, make_receipt, receipt_hash


def digest(character: str) -> str:
    return character * 64


class ReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = make_receipt(
            candidate_digest=digest("a"),
            decision="accept-provisional",
            reviewer_id="reviewer:" + digest("b"),
            checked_at="2026-08-26T22:15:00Z",
            corpus_digest=digest("c"),
            retrieval_digest=digest("d"),
        )

    def test_receipt(self) -> None:
        self.assertIs(check_receipt(self.receipt), self.receipt)
        self.assertEqual(self.receipt["reviewer_mode"], "declared-human")
        self.assertEqual(self.receipt["receipt_digest"], receipt_hash(self.receipt))
        self.assertEqual(
            self.receipt["scope"],
            {"corpus_digest": digest("c"), "retrieval_digest": digest("d")},
        )

    def test_decisions(self) -> None:
        for decision in ("accept-provisional", "hold", "reject"):
            receipt = make_receipt(
                candidate_digest=digest("a"),
                decision=decision,
                reviewer_id="reviewer:" + digest("b"),
                checked_at="2026-08-26T22:15:00Z",
                corpus_digest=digest("c"),
                retrieval_digest=digest("d"),
            )
            self.assertEqual(receipt["decision"], decision)
            check_receipt(receipt)

        for decision in ("reviewed", "accept", "approve", "automatic"):
            with self.subTest(decision=decision):
                with self.assertRaisesRegex(ValueError, "Review decision"):
                    make_receipt(
                        candidate_digest=digest("a"),
                        decision=decision,
                        reviewer_id="reviewer:" + digest("b"),
                        checked_at="2026-08-26T22:15:00Z",
                        corpus_digest=digest("c"),
                        retrieval_digest=digest("d"),
                    )

    def test_opaque_reviewer(self) -> None:
        for reviewer in (
            "alice@example.com",
            "Alice Example",
            "@private_handle",
            "reviewer:private-repo",
            "reviewer:" + "B" * 64,
        ):
            with self.subTest(reviewer=reviewer):
                with self.assertRaisesRegex(ValueError, "not opaque"):
                    make_receipt(
                        candidate_digest=digest("a"),
                        decision="hold",
                        reviewer_id=reviewer,
                        checked_at="2026-08-26T22:15:00Z",
                        corpus_digest=digest("c"),
                        retrieval_digest=digest("d"),
                    )

    def test_declared_only(self) -> None:
        changed = {**self.receipt, "reviewer_mode": "automatic"}
        changed["receipt_digest"] = receipt_hash(changed)

        with self.assertRaisesRegex(ValueError, "Reviewer mode"):
            check_receipt(changed)

    def test_timestamp(self) -> None:
        for checked_at in (
            "2026-02-30T22:15:00Z",
            "2026-08-26T22:15:00-07:00",
            "2026-08-26T22:15:00.123Z",
            "2026-08-26",
        ):
            changed = {**self.receipt, "checked_at": checked_at}
            changed["receipt_digest"] = receipt_hash(changed)
            with self.subTest(checked_at=checked_at):
                with self.assertRaisesRegex(ValueError, "timestamp"):
                    check_receipt(changed)

    def test_exact_keys(self) -> None:
        for field, value in (
            ("reviewed", True),
            ("reviewer_email", "alice@example.com"),
            ("notes", "free text"),
        ):
            changed = {**self.receipt, field: value}
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "receipt fields"):
                    check_receipt(changed)

        changed = copy.deepcopy(self.receipt)
        changed["scope"]["query"] = "private text"
        with self.assertRaisesRegex(ValueError, "scope fields"):
            check_receipt(changed)

        changed = copy.deepcopy(self.receipt)
        changed["scope"]["search_digest"] = changed["scope"].pop("retrieval_digest")
        with self.assertRaisesRegex(ValueError, "scope fields"):
            check_receipt(changed)

    def test_scope(self) -> None:
        for field in ("corpus_digest", "retrieval_digest"):
            changed = copy.deepcopy(self.receipt)
            changed["scope"][field] = digest("A")
            changed["receipt_digest"] = receipt_hash(changed)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "scope digests"):
                    check_receipt(changed)

    def test_tampering(self) -> None:
        for field, value in (
            ("candidate_digest", digest("e")),
            ("decision", "reject"),
            ("checked_at", "2026-08-26T22:16:00Z"),
        ):
            changed = {**self.receipt, field: value}
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "Receipt digest"):
                    check_receipt(changed)


if __name__ == "__main__":
    unittest.main()
