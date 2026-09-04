from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from archive import shard_meta, write_shard  # noqa: E402
from attest import (  # noqa: E402
    attest_digest,
    check_attestation,
    main,
    make_attestation,
)
from packet import CHECKLIST_FIELDS, make_triage_packet  # noqa: E402
from retrieve import retrieve  # noqa: E402
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


class AttestTests(unittest.TestCase):
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
        self.manifest = make_manifest("attest-test-1", sources)
        self.candidate = make_candidate(
            self.manifest,
            kind="idea",
            identity={
                "target": "agent reliability",
                "intervention": "sparse routing",
                "mechanism": "controlled expert selection",
                "outcome": "robust task success",
            },
            support_ids=[f"arxiv:{row['id']}" for row in self.papers[:6]],
            source_hashes=sources,
            retrieval=sources,
        )
        rows = [
            make_row(source, self.shard, row)
            for row, source in enumerate(self.papers[:6])
        ]
        self.support = build_bundle(rows, self.manifest["corpus_digest"])
        self.retrieval = retrieve(
            self.candidate,
            self.papers,
            corpus_scope=self.manifest["corpus_digest"],
        )
        self.packet = make_triage_packet(
            self.candidate,
            self.manifest,
            self.retrieval,
            self.support,
            archive_root=self.root,
        )
        self.review = {
            "reviewer_id": "reviewer:" + "e" * 64,
            "checked_at": "2026-09-03T20:15:00Z",
            "decision": "accept-provisional",
            "checklist": {field: "pass" for field in CHECKLIST_FIELDS},
        }

    def make(self, review: dict | None = None, packet: dict | None = None) -> dict:
        return make_attestation(
            packet or self.packet,
            self.candidate,
            self.manifest,
            self.retrieval,
            self.support,
            review or self.review,
            archive_root=self.root,
        )

    def check(self, value: object, packet: dict | None = None) -> dict:
        return check_attestation(
            value,
            packet or self.packet,
            self.candidate,
            self.manifest,
            self.retrieval,
            self.support,
            archive_root=self.root,
        )

    def test_binding(self) -> None:
        value = self.make()

        self.assertIs(self.check(value), value)
        self.assertEqual(value, self.make())
        self.assertEqual(value["packet_digest"], self.packet["packet_digest"])
        self.assertEqual(
            value["candidate_digest"], self.packet["lineage"]["candidate_digest"]
        )
        self.assertEqual(
            value["corpus_digest"], self.packet["lineage"]["corpus_digest"]
        )
        self.assertEqual(
            value["retrieval_digest"], self.packet["lineage"]["retrieval_digest"]
        )
        self.assertEqual(
            value["support_digest"], self.packet["lineage"]["support_digest"]
        )
        self.assertIn("not authenticated proof", value["notice"])
        self.assertNotIn("idea", value)

    def test_decisions(self) -> None:
        for decision, verdict in (
            ("accept-provisional", "pass"),
            ("hold", "hold"),
            ("reject", "reject"),
        ):
            with self.subTest(decision=decision):
                review = copy.deepcopy(self.review)
                review["decision"] = decision
                review["checklist"]["identity_distinctness"] = verdict
                self.assertEqual(self.make(review)["decision"], decision)

        review = copy.deepcopy(self.review)
        review["decision"] = "hold"
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.make(review)

        review["decision"] = "reject"
        review["checklist"]["identity_distinctness"] = "hold"
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.make(review)

    def test_explicit(self) -> None:
        for changed in ("pending-human-review", "", None, [], {}):
            with self.subTest(changed=changed):
                review = copy.deepcopy(self.review)
                review["checklist"]["retrieval_inspected"] = changed
                with self.assertRaisesRegex(
                    ValueError, "explicit pass, hold, or reject"
                ):
                    self.make(review)

        for operation in ("missing", "extra"):
            with self.subTest(operation=operation):
                review = copy.deepcopy(self.review)
                if operation == "missing":
                    del review["checklist"]["no_novelty_claim"]
                else:
                    review["checklist"]["automatic_promotion"] = "pass"
                with self.assertRaisesRegex(ValueError, "checklist fields"):
                    self.make(review)

    def test_lineage(self) -> None:
        value = self.make()
        fields = (
            "packet_digest",
            "candidate_digest",
            "corpus_digest",
            "retrieval_digest",
            "support_digest",
        )
        for field in fields:
            with self.subTest(field=field):
                changed = copy.deepcopy(value)
                changed[field] = "f" * 64
                changed["attestation_digest"] = attest_digest(changed)
                with self.assertRaisesRegex(ValueError, "checked packet"):
                    self.check(changed)

    def test_packet(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["candidate"]["identity"]["target"] = "tampered"
        with self.assertRaisesRegex(ValueError, "digest"):
            self.make(packet=changed)

    def test_closed(self) -> None:
        value = self.make()
        value["published"] = True
        value["attestation_digest"] = attest_digest(value)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            self.check(value)

        value = self.make()
        value["reviewer_mode"] = "automatic"
        value["attestation_digest"] = attest_digest(value)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            self.check(value)

    def write(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_cli(self) -> None:
        paths = {
            "packet": self.write("packet.json", self.packet),
            "candidate": self.write("candidate.json", self.candidate),
            "manifest": self.write("manifest.json", self.manifest),
            "retrieval": self.write("retrieval.json", self.retrieval),
            "support": self.write("support.json", self.support),
            "review": self.write("review.json", self.review),
        }
        output = self.root / "attestation.json"
        arguments = ["attest.py"]
        for name, path in paths.items():
            arguments.extend((f"--{name}", str(path)))
        arguments.extend(("--archive", str(self.root), "--output", str(output)))
        with patch.object(sys, "argv", arguments):
            main()
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), self.make())

        arguments.remove("--review")
        arguments.remove(str(paths["review"]))
        arguments.append("--check")
        with patch.object(sys, "argv", arguments):
            main()


if __name__ == "__main__":
    unittest.main()
