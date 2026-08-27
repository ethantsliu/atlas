import copy
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from approve import approve, approval_hash, check_approval  # noqa: E402
from archive import shard_meta, write_shard  # noqa: E402
from ontology import TOPICS, TRICKS  # noqa: E402
from retrieve import retrieval_digest, retrieve  # noqa: E402
from review import make_receipt, receipt_hash  # noqa: E402
from scan import make_ideas  # noqa: E402
from support import build_bundle, content_digest, make_row  # noqa: E402
from synth import make_candidate, make_manifest  # noqa: E402


def digest(character: str) -> str:
    return character * 64


def route(identifier: str) -> dict:
    return {"id": identifier, "score": 1, "evidence": [identifier]}


def paper(identifier: str, title: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://arxiv.org/abs/{identifier}",
        "title": title,
        "abstract": "We test sparse routing in controlled agents.",
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


def make_idea(papers: list[dict], manifest: dict) -> dict:
    supports = [(f"arxiv:{row['id']}", "2024-01") for row in papers]
    pairs = {
        ("agents", "routing-and-moe"): {
            "count": len(supports),
            "supports": supports,
        }
    }
    return make_ideas(pairs, manifest, 1)[0]


class ApproveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.papers = [
            paper("2401.00001", "First routing method"),
            paper("2401.00002", "Second routing method"),
            paper("2401.00003", "Third routing method"),
            paper("2401.00004", "Fourth routing method"),
        ]
        payload = {
            "schema_version": 1,
            "policy_version": "fixture-1",
            "month": "2024-01",
            "days": [],
            "counts": {"all": 4, "likely": 4, "possible": 0, "outside": 0},
            "papers": self.papers,
        }
        self.path = write_shard(self.root, payload)
        self.shard = shard_meta(self.path)
        sources = [{"source_id": "arxiv:2024-01", "sha256": self.shard["sha256"]}]
        self.manifest = make_manifest("discover-1", sources)
        self.candidate = make_idea(self.papers[:2], self.manifest)
        self.support = self.make_bundle(self.candidate)
        self.retrieval = retrieve(
            self.candidate,
            self.papers,
            corpus_scope=self.manifest["corpus_digest"],
        )
        self.receipt = self.make_review(self.candidate, self.retrieval)

    def make_bundle(self, candidate: dict) -> dict:
        identifiers = set(candidate["support_ids"])
        rows = [
            make_row(source, self.shard, row)
            for row, source in enumerate(self.papers)
            if f"arxiv:{source['id']}" in identifiers
        ]
        return build_bundle(rows, candidate["corpus_digest"])

    def make_review(
        self,
        candidate: dict,
        retrieval: dict,
        decision: str = "accept-provisional",
    ) -> dict:
        return make_receipt(
            candidate_digest=candidate["candidate_digest"],
            decision=decision,
            reviewer_id="reviewer:" + digest("e"),
            checked_at="2026-08-26T22:15:00Z",
            corpus_digest=candidate["corpus_digest"],
            retrieval_digest=retrieval["retrieval_digest"],
        )

    def accept(
        self,
        candidate: dict | None = None,
        receipt: dict | None = None,
        retrieval: dict | None = None,
        support: dict | None = None,
        manifest: dict | None = None,
    ) -> dict:
        return approve(
            candidate or self.candidate,
            manifest or self.manifest,
            receipt or self.receipt,
            retrieval or self.retrieval,
            support or self.support,
            archive_root=self.root,
        )

    def test_approval(self) -> None:
        record = self.accept()

        self.assertIs(check_approval(record), record)
        self.assertEqual(record["status"], "provisional")
        self.assertEqual(record["decision"], "accept-provisional")
        self.assertEqual(record["support_ids"], self.candidate["support_ids"])
        self.assertEqual(record["retrieval_digest"], self.retrieval["retrieval_digest"])
        self.assertNotEqual(record["retrieval_digest"], record["support_digest"])
        self.assertEqual(record["approval_digest"], approval_hash(record))
        self.assertEqual(record, self.accept())

    def test_archive_required(self) -> None:
        with self.assertRaises(TypeError):
            approve(
                self.candidate,
                self.manifest,
                self.receipt,
                self.retrieval,
                self.support,
            )

        with self.assertRaisesRegex(ValueError, "archive root"):
            approve(
                self.candidate,
                self.manifest,
                self.receipt,
                self.retrieval,
                self.support,
                archive_root=None,
            )

    def test_binds_candidate(self) -> None:
        changed = {**self.receipt, "candidate_digest": digest("f")}
        changed["receipt_digest"] = receipt_hash(changed)
        with self.assertRaisesRegex(ValueError, "candidate digest"):
            self.accept(receipt=changed)

        changed = copy.deepcopy(self.candidate)
        changed["identity"]["outcome"] = "different signal"
        with self.assertRaisesRegex(ValueError, "Candidate ID"):
            self.accept(candidate=changed)

    def test_binds_generation(self) -> None:
        changed = copy.deepcopy(self.receipt)
        changed["scope"]["corpus_digest"] = digest("f")
        changed["receipt_digest"] = receipt_hash(changed)
        with self.assertRaisesRegex(ValueError, "corpus generation"):
            self.accept(receipt=changed)

        other = make_manifest("discover-2", self.manifest["source_hashes"])
        with self.assertRaisesRegex(ValueError, "generator version"):
            self.accept(manifest=other)

    def test_binds_support(self) -> None:
        alternate = make_idea(self.papers[2:], self.manifest)
        support = self.make_bundle(alternate)
        with self.assertRaisesRegex(ValueError, "support-paper IDs"):
            self.accept(support=support)

    def test_binds_retrieval(self) -> None:
        changed = copy.deepcopy(self.receipt)
        changed["scope"]["retrieval_digest"] = digest("f")
        changed["receipt_digest"] = receipt_hash(changed)
        with self.assertRaisesRegex(ValueError, "retrieval digest"):
            self.accept(receipt=changed)

        changed = copy.deepcopy(self.retrieval)
        changed["candidate_id"] = "idea:" + digest("f")
        changed["retrieval_digest"] = retrieval_digest(changed)
        with self.assertRaisesRegex(ValueError, "candidate ID"):
            self.accept(retrieval=changed)

        changed = copy.deepcopy(self.retrieval)
        changed["retrieval_digest"] = digest("f")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.accept(retrieval=changed)

        changed = copy.deepcopy(self.retrieval)
        changed["retrieval_corpus_digest"] = digest("f")
        changed["retrieval_digest"] = retrieval_digest(changed)
        receipt = self.make_review(self.candidate, changed)
        with self.assertRaisesRegex(ValueError, "corpus generation"):
            self.accept(retrieval=changed, receipt=receipt)

    def test_lineage(self) -> None:
        sources = [{"source_id": "arxiv:2024-01", "sha256": digest("f")}]
        manifest = make_manifest("discover-1", sources)
        candidate = make_candidate(
            manifest,
            kind="idea",
            identity=self.candidate["identity"],
            support_ids=self.candidate["support_ids"],
            source_hashes=sources,
            retrieval=sources,
        )
        support = build_bundle(self.support["papers"], manifest["corpus_digest"])
        receipt = self.make_review(candidate, self.retrieval)

        with self.assertRaisesRegex(ValueError, "archive lineage"):
            self.accept(
                candidate=candidate,
                receipt=receipt,
                support=support,
                manifest=manifest,
            )

    def test_declared_gate(self) -> None:
        for decision in ("hold", "reject"):
            with self.subTest(decision=decision):
                receipt = self.make_review(self.candidate, self.retrieval, decision)
                with self.assertRaisesRegex(ValueError, "did not approve"):
                    self.accept(receipt=receipt)

        rejected = make_candidate(
            self.manifest,
            kind="idea",
            identity=self.candidate["identity"],
            support_ids=self.candidate["support_ids"],
            source_hashes=self.candidate["source_hashes"],
            retrieval=self.candidate["retrieval_sources"],
            review_status="rejected",
        )
        receipt = self.make_review(rejected, self.retrieval)
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            self.accept(candidate=rejected, receipt=receipt)

    def test_forged_rows(self) -> None:
        changes = []
        title = copy.deepcopy(self.support)
        title["papers"][0]["title"] = "Self-hashed forged title"
        changes.append(title)

        rows = copy.deepcopy(self.support)
        first = rows["papers"][0]["archive"]["row"]
        rows["papers"][0]["archive"]["row"] = rows["papers"][1]["archive"]["row"]
        rows["papers"][1]["archive"]["row"] = first
        changes.append(rows)

        shard = copy.deepcopy(self.support)
        for item in shard["papers"]:
            item["archive"]["sha256"] = digest("f")
        changes.append(shard)

        for changed in changes:
            changed["content_sha256"] = content_digest(changed)
            with self.subTest(change=changed["papers"][0]):
                with self.assertRaisesRegex(RuntimeError, "archive"):
                    self.accept(support=changed)

    def test_discover_flow(self) -> None:
        left = make_idea(self.papers[:2], self.manifest)
        right = make_idea(self.papers[2:], self.manifest)
        left_bundle = self.make_bundle(left)
        right_bundle = self.make_bundle(right)
        left_retrieval = retrieve(
            left, self.papers, corpus_scope=self.manifest["corpus_digest"]
        )
        right_retrieval = retrieve(
            right, self.papers, corpus_scope=self.manifest["corpus_digest"]
        )
        left_receipt = self.make_review(left, left_retrieval)
        right_receipt = self.make_review(right, right_retrieval)

        self.assertEqual(left["source_hashes"], right["source_hashes"])
        self.assertEqual(left["candidate_id"], right["candidate_id"])
        self.assertNotEqual(left["support_ids"], right["support_ids"])
        self.assertNotEqual(left["candidate_digest"], right["candidate_digest"])
        self.assertEqual(
            self.accept(
                candidate=left,
                receipt=left_receipt,
                retrieval=left_retrieval,
                support=left_bundle,
            )["support_ids"],
            left["support_ids"],
        )
        self.assertEqual(
            self.accept(
                candidate=right,
                receipt=right_receipt,
                retrieval=right_retrieval,
                support=right_bundle,
            )["support_ids"],
            right["support_ids"],
        )
        with self.assertRaisesRegex(ValueError, "support-paper IDs"):
            self.accept(
                candidate=left,
                receipt=left_receipt,
                retrieval=left_retrieval,
                support=right_bundle,
            )

    def test_no_claims(self) -> None:
        topics = copy.deepcopy(TOPICS)
        tricks = copy.deepcopy(TRICKS)
        record = self.accept()
        encoded = repr(record).lower()

        self.assertNotIn("researched-draft", encoded)
        self.assertNotIn("novelty", encoded)
        self.assertNotIn("competition", encoded)
        self.assertNotIn("topic", encoded)
        self.assertNotIn("trick_ids", encoded)
        self.assertEqual(TOPICS, topics)
        self.assertEqual(TRICKS, tricks)

    def test_exact_record(self) -> None:
        record = self.accept()
        for field, value in (
            ("brief", {}),
            ("novelty", "first"),
            ("topic_ids", ["agents"]),
        ):
            changed = {**record, field: value}
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "record fields"):
                    check_approval(changed)

    def test_tampering(self) -> None:
        record = self.accept()
        for field, value in (
            ("status", "researched-draft"),
            ("decision", "automatic"),
            ("approval_digest", digest("f")),
        ):
            changed = {**record, field: value}
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    check_approval(changed)

        changed = copy.deepcopy(record)
        changed["support_ids"].reverse()
        changed["approval_digest"] = approval_hash(changed)
        with self.assertRaisesRegex(ValueError, "support-paper IDs"):
            check_approval(changed)


if __name__ == "__main__":
    unittest.main()
