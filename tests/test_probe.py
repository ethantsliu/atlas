import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from probe import (  # noqa: E402
    PAPER_LIMIT,
    Fetched,
    ProbeError,
    parse_base,
    probe_many,
    run_probe,
)


def encoded(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


class FakeFetch:
    def __init__(self, responses: dict[str, tuple[str, bytes]]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def __call__(self, url: str, limit: int) -> Fetched:
        self.requests.append(url)
        content_type, body = self.responses[url]
        if len(body) > limit:
            raise ProbeError("fixture exceeds limit")
        return Fetched(url=url, status=200, content_type=content_type, body=body)


def fixture() -> tuple[FakeFetch, dict]:
    base = "https://example.org/atlas/"
    release_sha = "1" * 40
    reading = encoded({"stable_id": "arxiv:1", "reading_depth": "verified"})
    bundle = {
        "schema_version": 1,
        "papers": [
            {
                "stable_id": "arxiv:1",
                "full_reading_path": "/data/readings/arxiv-1--aaa-bbb.json",
            }
        ],
        "layout": {},
    }
    paper_bytes = encoded(bundle)
    core = {
        "schema_version": 2,
        "paper_asset": {
            "path": "/data/papers/" + hashlib.sha256(paper_bytes).hexdigest() + ".json",
            "sha256": hashlib.sha256(paper_bytes).hexdigest(),
            "bytes": len(paper_bytes),
        },
    }
    index = {
        "schema_version": 1,
        "days": [{"date": "2026-08-24", "path": "/data/feed/2026-08-24.json"}],
    }
    first = struct.pack("<8sI3fB", b"ATLASPT1", 1, 1.0, 2.0, 3.0, 0)
    latest = struct.pack("<8sI3fB", b"ATLASPT1", 1, 4.0, 5.0, 6.0, 1)
    cloud = {
        "schema_version": 1,
        "source": "arxiv",
        "point_bytes": 13,
        "count": 2,
        "counts": {"likely": 1, "possible": 1, "outside": 0},
        "shards": [
            {
                "month": "1991-01",
                "count": 1,
                "counts": {"likely": 1, "possible": 0, "outside": 0},
                "points": {
                    "path": "1991-01.bin",
                    "sha256": hashlib.sha256(first).hexdigest(),
                    "bytes": len(first),
                },
            },
            {
                "month": "2026-08",
                "count": 1,
                "counts": {"likely": 0, "possible": 1, "outside": 0},
                "points": {
                    "path": "2026-08.bin",
                    "sha256": hashlib.sha256(latest).hexdigest(),
                    "bytes": len(latest),
                },
            },
        ],
    }
    responses = {
        base + "release.json": (
            "application/json",
            encoded({"schema_version": 1, "sha": release_sha}),
        ),
        base + f"release.json?sha={release_sha}": (
            "application/json",
            encoded({"schema_version": 1, "sha": release_sha}),
        ),
        base: (
            "text/html",
            b'<div id="root"></div><script type="module" src="/atlas/assets/app.js"></script>',
        ),
        base + "assets/app.js": ("text/javascript", b"export{}"),
        base + "data/atlas.json": ("application/json", encoded(core)),
        base + core["paper_asset"]["path"].lstrip("/"): (
            "application/json",
            paper_bytes,
        ),
        base + "data/readings/arxiv-1--aaa-bbb.json": (
            "application/json",
            reading,
        ),
        base + "data/feed/index.json": ("application/json", encoded(index)),
        base + "data/feed/2026-08-24.json": (
            "application/json",
            encoded({"schema_version": 1, "date": "2026-08-24"}),
        ),
        base + "data/cloud/index.json": ("application/json", encoded(cloud)),
        base + "data/cloud/1991-01.bin": ("application/octet-stream", first),
        base + "data/cloud/2026-08.bin": ("application/octet-stream", latest),
    }
    return FakeFetch(responses), core


class ProbeTests(unittest.TestCase):
    def test_paper_limit(self) -> None:
        self.assertEqual(PAPER_LIMIT, 10_000_000)

    def test_deploy_gate(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.event == 'push'", workflow)
        self.assertIn(
            "github.event.workflow_run.event == 'workflow_dispatch'", workflow
        )
        self.assertIn("github.event.workflow_run.head_repository.full_name", workflow)
        self.assertIn("ref: ${{ github.event.workflow_run.head_sha }}", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertNotIn("make check", workflow)
        bind = workflow.index("Bind successful check and reject stale main")
        cloud = workflow.index("python pipeline/cloudpub.py")
        marker = workflow.index("web/dist/release.json")
        stale_sync = workflow.index("Reject stale corpus sync")
        sync = workflow.index("python pipeline/sync.py --corpus-only")
        upload = workflow.index("actions/upload-pages-artifact@v4")
        stale_publish = workflow.index("Reject a release made stale during build")
        deploy = workflow.index("actions/deploy-pages@v4")
        probe = workflow.index("python3 pipeline/probe.py")
        self.assertIn('--expected-sha "$CERTIFIED_SHA"', workflow)
        self.assertLess(bind, cloud)
        self.assertLess(cloud, marker)
        self.assertLess(marker, stale_sync)
        self.assertLess(cloud, stale_sync)
        self.assertLess(stale_sync, sync)
        self.assertLess(sync, upload)
        self.assertLess(upload, deploy)
        self.assertLess(stale_publish, deploy)
        self.assertLess(deploy, probe)

    def test_probe_schedule(self) -> None:
        workflow = (ROOT / ".github/workflows/probe.yml").read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('python3 pipeline/probe.py --base-url "$target"', workflow)

    def test_complete_release(self) -> None:
        fetcher, core = fixture()
        report = run_probe("https://example.org/atlas", fetcher)
        self.assertEqual(report["release_sha"], "1" * 40)
        self.assertEqual(report["paper_asset"], core["paper_asset"]["path"])
        self.assertEqual(report["paper_count"], 1)
        self.assertTrue(report["reading"].endswith("aaa-bbb.json"))
        self.assertTrue(report["feed"].endswith("2026-08-24.json"))
        self.assertEqual(report["cloud_count"], 2)
        self.assertEqual(len(report["cloud_assets"]), 2)
        self.assertEqual(len(fetcher.requests), 11)

    def test_exact_release(self) -> None:
        fetcher, _ = fixture()
        report = run_probe("https://example.org/atlas", fetcher, "1" * 40)
        self.assertEqual(report["release_sha"], "1" * 40)
        self.assertEqual(
            fetcher.requests[0],
            "https://example.org/atlas/release.json?sha=" + "1" * 40,
        )

    def test_stale_release(self) -> None:
        fetcher, _ = fixture()
        url = "https://example.org/atlas/release.json?sha=" + "1" * 40
        fetcher.responses[url] = (
            "application/json",
            encoded({"schema_version": 1, "sha": "2" * 40}),
        )
        with self.assertRaisesRegex(ProbeError, "certified SHA"):
            run_probe("https://example.org/atlas", fetcher, "1" * 40)

    def test_bad_digest(self) -> None:
        fetcher, _ = fixture()
        core_url = "https://example.org/atlas/data/atlas.json"
        content_type, body = fetcher.responses[core_url]
        core = json.loads(body)
        core["paper_asset"]["sha256"] = "0" * 64
        fetcher.responses[core_url] = (content_type, encoded(core))
        with self.assertRaisesRegex(ProbeError, "digest"):
            run_probe("https://example.org/atlas/", fetcher)

    def test_optional_assets(self) -> None:
        fetcher, core = fixture()
        base = "https://example.org/atlas/"
        old_url = base + core["paper_asset"]["path"].lstrip("/")
        bundle = {
            "schema_version": 1,
            "papers": [{"stable_id": "arxiv:1"}],
            "layout": {},
        }
        paper_bytes = encoded(bundle)
        digest = hashlib.sha256(paper_bytes).hexdigest()
        core["paper_asset"] = {
            "path": f"/data/papers/{digest}.json",
            "sha256": digest,
            "bytes": len(paper_bytes),
        }
        del fetcher.responses[old_url]
        fetcher.responses[base + "data/atlas.json"] = (
            "application/json",
            encoded(core),
        )
        fetcher.responses[base + f"data/papers/{digest}.json"] = (
            "application/json",
            paper_bytes,
        )
        fetcher.responses[base + "data/feed/index.json"] = (
            "application/json",
            encoded({"schema_version": 1, "days": []}),
        )
        report = run_probe(base, fetcher)
        self.assertIsNone(report["reading"])
        self.assertIsNone(report["feed"])

    def test_path_escape(self) -> None:
        fetcher, _ = fixture()
        html_url = "https://example.org/atlas/"
        fetcher.responses[html_url] = (
            "text/html",
            b'<div id="root"></div><script type="module" src="https://evil.example/app.js"></script>',
        )
        with self.assertRaisesRegex(ProbeError, "escapes"):
            run_probe(html_url, fetcher)

    def test_cloud_digest(self) -> None:
        fetcher, _ = fixture()
        url = "https://example.org/atlas/data/cloud/index.json"
        content_type, body = fetcher.responses[url]
        cloud = json.loads(body)
        cloud["shards"][0]["points"]["sha256"] = "0" * 64
        fetcher.responses[url] = (content_type, encoded(cloud))
        with self.assertRaisesRegex(ProbeError, "Cloud point digest"):
            run_probe("https://example.org/atlas/", fetcher)

    def test_cloud_shape(self) -> None:
        fetcher, _ = fixture()
        url = "https://example.org/atlas/data/cloud/index.json"
        content_type, body = fetcher.responses[url]
        cloud = json.loads(body)
        cloud["count"] = 3
        fetcher.responses[url] = (content_type, encoded(cloud))
        with self.assertRaisesRegex(ProbeError, "counts or ordering"):
            run_probe("https://example.org/atlas/", fetcher)

    def test_retry(self) -> None:
        fetcher, _ = fixture()
        calls = 0

        def flaky(url: str, limit: int) -> Fetched:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ProbeError("not propagated")
            return fetcher(url, limit)

        report = probe_many("https://example.org/atlas/", 2, 0, flaky)
        self.assertEqual(report["paper_count"], 1)
        self.assertEqual(calls, 12)

    def test_local_base(self) -> None:
        self.assertEqual(
            parse_base("http://127.0.0.1:4173/atlas"),
            "http://127.0.0.1:4173/atlas/",
        )
        with self.assertRaises(ProbeError):
            parse_base("http://example.org/atlas/")


if __name__ == "__main__":
    unittest.main()
