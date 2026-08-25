from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from competitors import (  # noqa: E402
    LEGACY_UNVERSIONED,
    PROVENANCE_SCHEMA_VERSION,
    VERSION_VERIFIED,
    merge_competitors,
    validate_provenance_payload,
)
from refresh import build_payload, collect_sources  # noqa: E402


def ideas() -> list[dict]:
    competitor = {
        "canonical_id": "arxiv:1234.56789",
        "title": "A Primary Paper",
        "url": "https://arxiv.org/abs/1234.56789",
        "relationship": "closest work",
        "difference": "The proposal adds a sealed test.",
    }
    return [
        {"id": "one", "brief": {"competitive_landscape": [competitor]}},
        {
            "id": "two",
            "brief": {"competitive_landscape": [{**competitor}]},
        },
    ]


def verified_record() -> dict:
    return {
        "provenance_status": VERSION_VERIFIED,
        "source_kind": "arxiv",
        "source_version": "arXiv:1234.56789v3",
        "source_date": "2026-08-01",
        "checked_at": "2026-08-23",
        "source_locator": "https://arxiv.org/abs/1234.56789v3",
        "verified_title": "A Primary Paper",
    }


class CompetitorProvenanceTests(unittest.TestCase):
    def test_shared_record(self) -> None:
        source = ideas()
        before = deepcopy(source)

        merged = merge_competitors(source, {"arxiv:1234.56789": verified_record()})

        self.assertEqual(source, before)
        for idea in merged:
            competitor = idea["brief"]["competitive_landscape"][0]
            self.assertEqual(competitor["provenance_status"], VERSION_VERIFIED)
            self.assertEqual(competitor["source_version"], "arXiv:1234.56789v3")

    def test_invalid_records(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing IDs"):
            merge_competitors(ideas(), {})
        with self.assertRaisesRegex(RuntimeError, "stale IDs"):
            merge_competitors(
                ideas(),
                {
                    "arxiv:1234.56789": verified_record(),
                    "arxiv:extra": verified_record(),
                },
            )

        source = ideas()
        source[0]["brief"]["competitive_landscape"][0]["source_version"] = "v1"
        with self.assertRaisesRegex(RuntimeError, "conflicts with sidecar"):
            merge_competitors(source, {"arxiv:1234.56789": verified_record()})

    def test_legacy_metadata(self) -> None:
        legacy = {
            "provenance_status": LEGACY_UNVERSIONED,
            "source_kind": "official-proceedings",
            "checked_at": "2026-08-23",
            "source_locator": "https://papers.neurips.cc/paper",
            "verified_title": "Paper",
            "unresolved_reason": "The primary record publishes only a year.",
        }
        validate_provenance_payload(
            {
                "schema_version": PROVENANCE_SCHEMA_VERSION,
                "records": {"neurips:paper": legacy},
            }
        )
        with self.assertRaisesRegex(RuntimeError, "partial version metadata"):
            validate_provenance_payload(
                {
                    "schema_version": PROVENANCE_SCHEMA_VERSION,
                    "records": {
                        "neurips:paper": {**legacy, "source_version": "NeurIPS 2020"}
                    },
                }
            )

    def test_refresh_revision(self) -> None:
        sources = collect_sources(ideas())
        payload = build_payload(
            sources,
            {
                "1234.56789": {
                    "version": "v3",
                    "date": "2026-08-01",
                    "title": "A Primary Paper",
                }
            },
            {},
            "2026-08-23",
        )
        record = payload["records"]["arxiv:1234.56789"]
        self.assertEqual(record["source_version"], "arXiv:1234.56789v3")

        mismatched = build_payload(
            sources,
            {
                "1234.56789": {
                    "version": "v3",
                    "date": "2026-08-01",
                    "title": "A Different Paper",
                }
            },
            {},
            "2026-08-23",
        )
        self.assertEqual(
            mismatched["records"]["arxiv:1234.56789"]["provenance_status"],
            LEGACY_UNVERSIONED,
        )


if __name__ == "__main__":
    unittest.main()
