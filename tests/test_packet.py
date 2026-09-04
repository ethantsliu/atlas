import copy
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from archive import shard_meta, write_shard  # noqa: E402
from packet import (  # noqa: E402
    CHECKLIST_FIELDS,
    check_triage_packet,
    make_triage_packet,
    packet_digest,
)
from retrieve import retrieval_digest, retrieve  # noqa: E402
from support import build_bundle, make_row  # noqa: E402
from synth import make_candidate, make_manifest  # noqa: E402


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(index: int) -> dict:
    identifier = f"2401.{index:05d}"
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": f"Sparse routing for robust agent reliability study {index}",
        "abstract": (
            "We test controlled expert selection for robust agent reliability "
            "under sparse routing interventions."
        ),
        "authors": ["Ada Researcher"],
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "published": "2024-01-02T00:00:00Z",
        "updated": "2024-01-03T00:00:00Z",
        "scope": "likely",
        "relevance": {
            "relevant": True,
            "score": 8.0,
            "lane": "core",
            "reasons": ["core ML category"],
            "strong_hits": [],
            "support_hits": [],
        },
        "interest": {"score": 4.0, "reasons": []},
        "topics": [route("agents")],
        "tricks": [route("routing-and-moe")],
    }


class TriagePacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.papers = [paper(index) for index in range(1, 13)]
        payload = {
            "schema_version": 1,
            "policy_version": "fixture-1",
            "month": "2024-01",
            "days": [],
            "counts": {"all": 12, "likely": 12, "possible": 0, "outside": 0},
            "papers": self.papers,
        }
        self.path = write_shard(self.root, payload)
        self.shard = shard_meta(self.path)
        sources = [{"source_id": "arxiv:2024-01", "sha256": self.shard["sha256"]}]
        self.manifest = make_manifest("packet-test-1", sources)
        self.candidate = self.make_candidate(6)
        self.support = self.make_bundle(self.candidate)
        self.retrieval = retrieve(
            self.candidate,
            self.papers,
            corpus_scope=self.manifest["corpus_digest"],
        )

    def make_candidate(self, support_count: int, **changes: object) -> dict:
        values = {
            "kind": "idea",
            "identity": {
                "target": "agent reliability",
                "intervention": "sparse routing",
                "mechanism": "controlled expert selection",
                "outcome": "robust task success",
            },
            "support_ids": [
                f"arxiv:{row['id']}" for row in self.papers[:support_count]
            ],
            "source_hashes": self.manifest["source_hashes"],
            "retrieval": self.manifest["source_hashes"],
            "review_status": "unreviewed",
        }
        values.update(changes)
        return make_candidate(self.manifest, **values)

    def make_bundle(self, candidate: dict) -> dict:
        identifiers = set(candidate["support_ids"])
        rows = [
            make_row(source, self.shard, row)
            for row, source in enumerate(self.papers)
            if f"arxiv:{source['id']}" in identifiers
        ]
        return build_bundle(rows, candidate["corpus_digest"])

    def make_packet(
        self,
        *,
        candidate: dict | None = None,
        retrieval: dict | None = None,
        support: dict | None = None,
    ) -> dict:
        return make_triage_packet(
            candidate or self.candidate,
            self.manifest,
            retrieval or self.retrieval,
            support or self.support,
            archive_root=self.root,
        )

    def check(self, packet: object) -> dict:
        return check_triage_packet(
            packet,
            self.candidate,
            self.manifest,
            self.retrieval,
            self.support,
            archive_root=self.root,
        )

    def test_build(self) -> None:
        packet = self.make_packet()

        self.assertIs(self.check(packet), packet)
        self.assertEqual(packet, self.make_packet())
        self.assertEqual(packet["status"], "unreviewed")
        self.assertFalse(packet["review_gate"]["automatic_promotion"])
        self.assertEqual(
            packet["review_gate"]["required_receipt"],
            "separate-declared-human-receipt",
        )
        self.assertEqual(
            packet["checklist"],
            {field: "pending-human-review" for field in CHECKLIST_FIELDS},
        )
        self.assertEqual(len(packet["support_papers"]), 6)
        self.assertGreaterEqual(len(packet["retrieval_candidates"]), 5)

    def test_detachment(self) -> None:
        packet = self.make_packet()
        self.candidate["identity"]["target"] = "mutated"
        self.support["papers"][0]["title"] = "mutated"
        self.retrieval["candidates"][0]["shared_terms"][0] = "mutated"

        self.assertEqual(packet["candidate"]["identity"]["target"], "agent reliability")
        self.assertNotEqual(packet["support_papers"][0]["title"], "mutated")
        self.assertNotEqual(
            packet["retrieval_candidates"][0]["shared_terms"][0], "mutated"
        )

    def test_support_floor(self) -> None:
        candidate = self.make_candidate(5)
        support = self.make_bundle(candidate)
        retrieval = retrieve(
            candidate,
            self.papers,
            corpus_scope=self.manifest["corpus_digest"],
        )
        with self.assertRaisesRegex(ValueError, "at least 6 resolvable supports"):
            self.make_packet(candidate=candidate, retrieval=retrieval, support=support)

        self.path.unlink()
        with self.assertRaisesRegex(RuntimeError, "archive shard is missing"):
            self.make_packet()

    def test_retrieval_floor(self) -> None:
        retrieval = retrieve(
            self.candidate,
            self.papers[:10],
            corpus_scope=self.manifest["corpus_digest"],
        )
        self.assertEqual(len(retrieval["candidates"]), 4)
        with self.assertRaisesRegex(ValueError, "at least 5 retrieval candidates"):
            self.make_packet(retrieval=retrieval)

    def test_no_overlap(self) -> None:
        retrieval = copy.deepcopy(self.retrieval)
        retrieval["candidates"][0]["canonical_id"] = self.candidate["support_ids"][0]
        retrieval["retrieval_digest"] = retrieval_digest(retrieval)
        with self.assertRaisesRegex(ValueError, "overlap support papers"):
            self.make_packet(retrieval=retrieval)

    def test_unreviewed(self) -> None:
        trick = self.make_candidate(6, kind="trick")
        trick_support = self.make_bundle(trick)
        trick_retrieval = retrieve(
            trick,
            self.papers,
            corpus_scope=self.manifest["corpus_digest"],
        )
        with self.assertRaisesRegex(ValueError, "requires an idea"):
            self.make_packet(
                candidate=trick,
                retrieval=trick_retrieval,
                support=trick_support,
            )

        rejected = self.make_candidate(6, review_status="rejected")
        with self.assertRaisesRegex(ValueError, "requires an unreviewed candidate"):
            self.make_packet(candidate=rejected)

    def test_lineage(self) -> None:
        for field in (
            "corpus_digest",
            "candidate_digest",
            "retrieval_digest",
            "support_digest",
        ):
            with self.subTest(field=field):
                packet = self.make_packet()
                packet["lineage"][field] = "f" * 64
                packet["packet_digest"] = packet_digest(packet)
                with self.assertRaisesRegex(ValueError, "source artifacts"):
                    self.check(packet)

    def test_review_gate(self) -> None:
        changes = (
            ("status", "reviewed"),
            ("review_gate", {"automatic_promotion": True, "required_receipt": "x"}),
        )
        for field, changed in changes:
            with self.subTest(field=field):
                packet = self.make_packet()
                packet[field] = changed
                packet["packet_digest"] = packet_digest(packet)
                with self.assertRaisesRegex(ValueError, "schema violation"):
                    self.check(packet)

        packet = self.make_packet()
        packet["checklist"]["retrieval_inspected"] = "passed"
        packet["packet_digest"] = packet_digest(packet)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            self.check(packet)

    def test_closed_schema(self) -> None:
        packet = self.make_packet()
        packet["reviewer"] = "self-asserted"
        packet["packet_digest"] = packet_digest(packet)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            self.check(packet)


if __name__ == "__main__":
    unittest.main()
