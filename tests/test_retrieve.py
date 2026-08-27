from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import retrieve as retrieval_module  # noqa: E402
from retrieve import (  # noqa: E402
    check_retrieval,
    retrieval_digest,
    retrieve,
    retrieve_many,
)


CANDIDATE = {
    "candidate_id": "idea:" + "a" * 64,
    "identity": {
        "target": "optimizer stability",
        "intervention": "rarebridge search",
        "mechanism": "controlled optimization",
        "outcome": "stable search",
    },
    "support_ids": ["arxiv:2401.00003"],
}


def paper(
    identifier: str,
    title: str,
    abstract: str = "",
    categories: list[str] | None = None,
    **extra: object,
) -> dict:
    return {
        "arxiv_id": identifier,
        "title": title,
        "abstract": abstract,
        "categories": categories or ["cs.LG"],
        **extra,
    }


class CandidateRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            paper(
                "2401.00001v2",
                "Rarebridge optimizer stability",
                "A controlled optimizer stability study.",
            ),
            paper(
                "2401.00002",
                "Rarebridge search stability",
                "Search under stable optimization.",
            ),
            paper(
                "2401.00003",
                "Photon geometry",
                "A detector calibration study.",
                ["physics.optics"],
            ),
        ]

    def test_candidate_shape(self) -> None:
        result = retrieve(CANDIDATE, self.records, limit=2)

        self.assertEqual(result["candidate_id"], CANDIDATE["candidate_id"])
        self.assertEqual(result["status"], "candidate_only")
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "candidate_id",
                "status",
                "retrieval_corpus_digest",
                "candidates",
                "notice",
                "retrieval_digest",
            },
        )
        self.assertRegex(result["retrieval_corpus_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["retrieval_digest"], r"^[0-9a-f]{64}$")
        self.assertIs(check_retrieval(result), result)
        self.assertEqual(result["candidates"][0]["canonical_id"], "arxiv:2401.00002")
        self.assertEqual(result["candidates"][0]["status"], "candidate_only")
        self.assertEqual(
            set(result["candidates"][0]),
            {"canonical_id", "score", "shared_terms", "status"},
        )
        self.assertIn("rarebridge", result["candidates"][0]["shared_terms"])
        self.assertGreater(result["candidates"][0]["score"], 0)
        self.assertNotIn("title", result["candidates"][0])
        serialized = repr(result).lower()
        self.assertNotIn("novelty", serialized)
        self.assertNotIn("competition", serialized)

    def test_exclusions(self) -> None:
        records = [
            *self.records,
            paper("2401.00002v3", "Rarebridge duplicate"),
            paper("2401.00004", "Rarebridge deleted", deleted=True),
            paper(
                "2401.00005",
                "Rarebridge context",
                record_kind="non_paper_context",
            ),
            {
                "stable_id": "openreview:other",
                "title": "Rarebridge review",
                "abstract": "",
                "categories": ["cs.LG"],
            },
        ]

        result = retrieve(
            CANDIDATE,
            records,
            limit=10,
        )

        self.assertEqual(
            [item["canonical_id"] for item in result["candidates"]],
            ["arxiv:2401.00001", "arxiv:2401.00002"],
        )

    def test_stable_order(self) -> None:
        forward = retrieve(CANDIDATE, self.records)
        reverse = retrieve(CANDIDATE, list(reversed(self.records)))

        self.assertEqual(forward, reverse)

    def test_batch_reuse(self) -> None:
        other = {
            **CANDIDATE,
            "candidate_id": "idea:" + "b" * 64,
            "support_ids": [],
        }
        with (
            patch.object(
                retrieval_module,
                "public_row",
                wraps=retrieval_module.public_row,
            ) as public,
            patch.object(
                retrieval_module,
                "row_text",
                wraps=retrieval_module.row_text,
            ) as text,
        ):
            results = retrieve_many([CANDIDATE, other], self.records)

        self.assertEqual(
            [result["candidate_id"] for result in results],
            [CANDIDATE["candidate_id"], other["candidate_id"]],
        )
        self.assertEqual(public.call_count, len(self.records))
        self.assertEqual(text.call_count, len(self.records))

    def test_category_signal(self) -> None:
        records = [
            paper("2401.00001", "Alpha query", categories=["cs.LG"]),
            paper("2401.00002", "Beta candidate", categories=["cs.LG"]),
            paper("2401.00003", "Gamma candidate", categories=["math.AG"]),
        ]

        candidate = {
            **CANDIDATE,
            "identity": {
                "target": "cs.LG taxonomy",
                "intervention": "archive routing",
                "mechanism": "field alignment",
                "outcome": "grouping fidelity",
            },
            "support_ids": [],
        }
        result = retrieve(candidate, records)

        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(
            {item["canonical_id"] for item in result["candidates"]},
            {"arxiv:2401.00001", "arxiv:2401.00002"},
        )
        self.assertTrue(
            all("cs.lg" in item["shared_terms"] for item in result["candidates"])
        )

    def test_private_exclusion(self) -> None:
        records = [
            *self.records,
            paper("2401.00004", "Rarebridge /Users/account/private note"),
        ]

        result = retrieve(CANDIDATE, records)

        self.assertNotIn(
            "arxiv:2401.00004",
            {item["canonical_id"] for item in result["candidates"]},
        )
        self.assertNotRegex(repr(result), re.compile(r"/users/", re.IGNORECASE))

    def test_unsafe_exclusion(self) -> None:
        baseline = retrieve(CANDIDATE, self.records)
        unsafe = (
            "contact hidden@example.com",
            "follow @hiddenuser",
            "open file:///tmp/private.pdf",
            "read ../private/notes",
            r"read C:\Users\Name\private.txt",
            "open http://localhost:3000/private",
            "open http://127.0.0.1/private",
            "open http://192.168.1.7/private",
            "see https://github.com/private/project",
            "see https://discord.gg/private",
            "see https://twitter.com/privateuser/status/1",
            "contact hidden＠example.com",
            "hidden\u202etext",
            "zero\u200bwidth",
            "null\x00byte",
        )

        for offset, text in enumerate(unsafe, start=10):
            with self.subTest(text=repr(text)):
                row = paper(f"2401.000{offset}", f"Rarebridge {text}")
                result = retrieve(CANDIDATE, [*self.records, row])
                self.assertEqual(result, baseline)

    def test_legacy_identity(self) -> None:
        candidate = {
            **CANDIDATE,
            "support_ids": ["arxiv:hep-th/9901001"],
        }
        records = [
            paper("hep-th/9901001v3", "Rarebridge theory"),
            paper("hep-th/9901002", "Rarebridge analysis"),
        ]

        result = retrieve(candidate, records)

        self.assertEqual(result["candidate_id"], CANDIDATE["candidate_id"])
        self.assertEqual(
            result["candidates"][0]["canonical_id"], "arxiv:hep-th/9901002"
        )

    def test_invalid_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "Candidate ID"):
            retrieve({**CANDIDATE, "candidate_id": "idea-private"}, self.records)
        with self.assertRaisesRegex(ValueError, "identity fields"):
            retrieve({**CANDIDATE, "identity": {"target": "only"}}, self.records)
        with self.assertRaisesRegex(ValueError, "support IDs"):
            retrieve({**CANDIDATE, "support_ids": ["private-support"]}, self.records)
        private = {
            **CANDIDATE,
            "identity": {**CANDIDATE["identity"], "target": "/Users/name/private"},
        }
        with self.assertRaisesRegex(RuntimeError, "local device path"):
            retrieve(private, self.records)
        unsafe = {
            **CANDIDATE,
            "identity": {
                **CANDIDATE["identity"],
                "target": "contact hidden@example.com",
            },
        }
        with self.assertRaisesRegex(RuntimeError, "unsafe text"):
            retrieve(unsafe, self.records)
        with self.assertRaisesRegex(ValueError, "limit"):
            retrieve(CANDIDATE, self.records, limit=0)

    def test_tamper_checks(self) -> None:
        result = retrieve(CANDIDATE, self.records)
        changes = []

        extra = {**result, "review_status": "reviewed"}
        changes.append((extra, "artifact fields"))
        for field, value, message in (
            ("schema_version", 2, "schema version"),
            ("candidate_id", "idea:" + "b" * 64, "does not match"),
            ("status", "reviewed", "status"),
            ("retrieval_corpus_digest", "b" * 64, "does not match"),
            ("notice", "A changed notice", "status"),
            ("retrieval_digest", "b" * 64, "does not match"),
        ):
            changes.append(({**result, field: value}, message))

        for changed, message in changes:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    check_retrieval(changed)

    def test_row_tampering(self) -> None:
        result = retrieve(CANDIDATE, self.records)

        invalid = copy.deepcopy(result)
        invalid["candidates"][0]["score"] = 2.0
        invalid["retrieval_digest"] = retrieval_digest(invalid)
        with self.assertRaisesRegex(ValueError, "score"):
            check_retrieval(invalid)

        duplicate = copy.deepcopy(result)
        duplicate["candidates"].append(copy.deepcopy(duplicate["candidates"][0]))
        duplicate["retrieval_digest"] = retrieval_digest(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicated"):
            check_retrieval(duplicate)

        reordered = copy.deepcopy(result)
        reordered["candidates"] = list(reversed(reordered["candidates"]))
        reordered["retrieval_digest"] = retrieval_digest(reordered)
        with self.assertRaisesRegex(ValueError, "out of order"):
            check_retrieval(reordered)

        terms = copy.deepcopy(result)
        terms["candidates"][0]["shared_terms"] = ["same", "same"]
        terms["retrieval_digest"] = retrieval_digest(terms)
        with self.assertRaisesRegex(ValueError, "shared terms"):
            check_retrieval(terms)

        terms = copy.deepcopy(result)
        terms["candidates"][0]["shared_terms"] = list(
            reversed(terms["candidates"][0]["shared_terms"])
        )
        terms["retrieval_digest"] = retrieval_digest(terms)
        with self.assertRaisesRegex(ValueError, "shared terms"):
            check_retrieval(terms)


if __name__ == "__main__":
    unittest.main()
