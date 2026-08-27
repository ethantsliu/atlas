import copy
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from synth import (
    candidate_hash,
    check_candidate,
    check_manifest,
    corpus_digest,
    make_candidate,
    make_manifest,
    retrieval_hash,
)


def digest(character: str) -> str:
    return character * 64


SOURCES = [
    {"source_id": "arxiv:2020-02", "sha256": digest("d")},
    {"source_id": "arxiv:2020-01", "sha256": digest("c")},
]
RETRIEVAL = [
    *SOURCES,
    {"source_id": "arxiv:2019-12", "sha256": digest("e")},
]
CORPUS = [
    *RETRIEVAL,
    {"source_id": "arxiv:2020-03", "sha256": digest("b")},
    {"source_id": "arxiv:2020-04", "sha256": digest("a")},
]
SUPPORT_IDS = ["arxiv:2001.00001", "arxiv:2001.00002"]
IDENTITY = {
    "target": "reinforcement-learning environments",
    "intervention": "evolutionary environment search",
    "mechanism": "mechanism-discriminating fitness",
    "outcome": "transferable learning signal",
}


class SynthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = make_manifest("synth-1", CORPUS)
        self.candidate = make_candidate(
            self.manifest,
            kind="idea",
            identity=IDENTITY,
            support_ids=SUPPORT_IDS,
            source_hashes=SOURCES,
            retrieval=RETRIEVAL,
        )

    def test_manifest(self) -> None:
        self.assertEqual(
            self.manifest,
            {
                "schema_version": 1,
                "generator_version": "synth-1",
                "corpus_digest": corpus_digest(CORPUS),
                "source_hashes": sorted(CORPUS, key=lambda row: row["source_id"]),
            },
        )
        self.assertIs(check_manifest(self.manifest), self.manifest)
        self.assertEqual(corpus_digest(CORPUS), corpus_digest(list(reversed(CORPUS))))

    def test_candidate(self) -> None:
        self.assertIs(check_candidate(self.candidate, self.manifest), self.candidate)
        self.assertEqual(
            self.candidate["retrieval_sources"],
            sorted(RETRIEVAL, key=lambda row: row["source_id"]),
        )
        self.assertEqual(self.candidate["retrieval_hash"], retrieval_hash(RETRIEVAL))
        self.assertEqual(
            self.candidate["candidate_digest"], candidate_hash(self.candidate)
        )
        self.assertRegex(self.candidate["candidate_id"], r"^idea:[0-9a-f]{64}$")

    def test_stable_id(self) -> None:
        later = make_manifest(
            "synth-2",
            [*CORPUS, {"source_id": "arxiv:2020-05", "sha256": digest("f")}],
        )
        revised = make_candidate(
            later,
            kind="idea",
            identity=IDENTITY,
            support_ids=SUPPORT_IDS,
            source_hashes=[SOURCES[0]],
            retrieval=[RETRIEVAL[0]],
            review_status="rejected",
        )

        self.assertEqual(revised["candidate_id"], self.candidate["candidate_id"])
        self.assertNotEqual(
            revised["candidate_digest"], self.candidate["candidate_digest"]
        )

    def test_review_states(self) -> None:
        for status in ("unreviewed", "rejected"):
            candidate = make_candidate(
                self.manifest,
                kind="trick",
                identity=IDENTITY,
                support_ids=[SUPPORT_IDS[0]],
                source_hashes=SOURCES,
                retrieval=RETRIEVAL,
                review_status=status,
            )
            self.assertEqual(candidate["review_status"], status)
            check_candidate(candidate, self.manifest)

        for status in ("reviewed", "published"):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "Review status"):
                    make_candidate(
                        self.manifest,
                        kind="idea",
                        identity=IDENTITY,
                        support_ids=SUPPORT_IDS,
                        source_hashes=SOURCES,
                        retrieval=RETRIEVAL,
                        review_status=status,
                    )

    def test_exact_keys(self) -> None:
        manifest = {**self.manifest, "generated_at": "2026-08-26"}
        candidate = {**self.candidate, "prompt": "hidden mutable provenance"}

        with self.assertRaisesRegex(ValueError, "manifest fields"):
            check_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "candidate fields"):
            check_candidate(candidate, self.manifest)

    def test_tampering(self) -> None:
        for field, value, message in (
            ("corpus_digest", digest("0"), "corpus digest"),
            ("candidate_id", "idea:" + digest("0"), "Candidate ID"),
            ("candidate_digest", digest("0"), "Candidate digest"),
        ):
            changed = {**self.candidate, field: value}
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, message):
                    check_candidate(changed, self.manifest)

        changed = copy.deepcopy(self.candidate)
        changed["identity"]["outcome"] = "a different outcome"
        with self.assertRaisesRegex(ValueError, "Candidate ID"):
            check_candidate(changed, self.manifest)

    def test_source_rules(self) -> None:
        duplicate = [CORPUS[0], CORPUS[0]]
        extra = [{**CORPUS[0], "version": "v1"}]
        uppercase = [{"source_id": "arxiv:2020-01", "sha256": "A" * 64}]

        for rows, message in (
            (duplicate, "duplicated"),
            (extra, "fields"),
            (uppercase, "values"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    make_manifest("synth-1", rows)

    def test_binding(self) -> None:
        other = make_manifest(
            "synth-1",
            [{"source_id": "arxiv:2021-01", "sha256": digest("f")}],
        )
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            check_candidate(self.candidate, other)

    def test_source_binding(self) -> None:
        fabricated = {"source_id": "arxiv:9999.99999v1", "sha256": digest("9")}
        drifted = {**SOURCES[0], "sha256": digest("9")}

        for sources, retrieval, label in (
            ([fabricated], RETRIEVAL, "Candidate sources"),
            ([drifted], RETRIEVAL, "Candidate sources"),
            (SOURCES, [fabricated], "Retrieval sources"),
            (SOURCES, [drifted], "Retrieval sources"),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, label):
                    make_candidate(
                        self.manifest,
                        kind="idea",
                        identity=IDENTITY,
                        support_ids=SUPPORT_IDS,
                        source_hashes=sources,
                        retrieval=retrieval,
                    )

    def test_deleted_source(self) -> None:
        reduced = make_manifest(
            "synth-1",
            [row for row in CORPUS if row != SOURCES[0]],
        )
        rebound = {
            **self.candidate,
            "corpus_digest": reduced["corpus_digest"],
        }
        rebound["candidate_digest"] = candidate_hash(rebound)

        with self.assertRaisesRegex(ValueError, "Candidate sources"):
            check_candidate(rebound, reduced)

    def test_checked_sources(self) -> None:
        fabricated = {"source_id": "arxiv:9999.99999v1", "sha256": digest("9")}
        drifted = {**SOURCES[0], "sha256": digest("9")}

        for source in (fabricated, drifted):
            changed = {**self.candidate, "source_hashes": [source]}
            changed["candidate_digest"] = candidate_hash(changed)
            with self.subTest(source=source["source_id"]):
                with self.assertRaisesRegex(ValueError, "Candidate sources"):
                    check_candidate(changed, self.manifest)

    def test_retrieval_tamper(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["retrieval_sources"][0]["sha256"] = digest("9")

        with self.assertRaisesRegex(ValueError, "Retrieval sources"):
            check_candidate(changed, self.manifest)

    def test_support_ids(self) -> None:
        for kind, supports, message in (
            ("idea", [SUPPORT_IDS[0]], "Idea support is incomplete"),
            ("idea", [SUPPORT_IDS[0], SUPPORT_IDS[0]], "duplicated"),
            ("idea", list(reversed(SUPPORT_IDS)), "not sorted"),
            ("idea", ["arxiv:2001.00001v2", SUPPORT_IDS[1]], "version-free"),
            ("trick", [], "Trick support is incomplete"),
        ):
            with self.subTest(kind=kind, supports=supports):
                with self.assertRaisesRegex(ValueError, message):
                    make_candidate(
                        self.manifest,
                        kind=kind,
                        identity=IDENTITY,
                        support_ids=supports,
                        source_hashes=SOURCES,
                        retrieval=RETRIEVAL,
                    )

    def test_support_digest(self) -> None:
        alternate = make_candidate(
            self.manifest,
            kind="idea",
            identity=IDENTITY,
            support_ids=["arxiv:2001.00001", "arxiv:2001.00003"],
            source_hashes=SOURCES,
            retrieval=RETRIEVAL,
        )

        self.assertEqual(alternate["source_hashes"], self.candidate["source_hashes"])
        self.assertEqual(alternate["candidate_id"], self.candidate["candidate_id"])
        self.assertNotEqual(
            alternate["candidate_digest"], self.candidate["candidate_digest"]
        )

    def test_identity_privacy(self) -> None:
        unsafe = (
            "/Users/alice/private/project",
            "/home/alice/private/project",
            "C:\\Users\\alice\\private\\project",
            "/tmp/private/project",
            "../private/project",
            "file:///tmp/private/project",
            "ｆｉｌｅ：／／／tmp/private/project",
            "alice@example.org",
            "@private_handle",
            "＠private_handle",
            "https://twitter.com/private_handle",
            "https://github.com/alice/private-repo",
            "http://localhost:3000/private",
            "private repository",
            "local device name",
            "host name: workstation-12",
            "codex workspace",
            "sample-overleaf",
            "left\u202eright",
            "zero\u200bwidth",
            "escape\x1bcode",
            "surrogate\ud800text",
            "line\nbreak",
            "x" * 241,
        )
        for text in unsafe:
            identity = {**IDENTITY, "mechanism": text}
            with self.subTest(text=repr(text)):
                with self.assertRaisesRegex(
                    ValueError, "Candidate identity values are invalid"
                ) as raised:
                    make_candidate(
                        self.manifest,
                        kind="idea",
                        identity=identity,
                        support_ids=SUPPORT_IDS,
                        source_hashes=SOURCES,
                        retrieval=RETRIEVAL,
                    )
                self.assertNotIn(text, str(raised.exception))

    def test_identity_tamper(self) -> None:
        changed = copy.deepcopy(self.candidate)
        changed["identity"]["target"] = "private repository"
        changed["candidate_digest"] = candidate_hash(changed)

        with self.assertRaisesRegex(ValueError, "identity values"):
            check_candidate(changed, self.manifest)


if __name__ == "__main__":
    unittest.main()
