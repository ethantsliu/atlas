import { describe, expect, it, vi } from "vitest";
import { fetchArchive, isArchiveManifest } from "./archive";

const manifest = {
  schema_version: 1,
  storage: "github-release",
  retention: "all metadata; no scope is discarded",
  counts: { all: 3, likely: 1, possible: 1, outside: 1 },
  shards: [
    {
      month: "2020-01",
      path: "2020-01.json.gz",
      sha256: "a".repeat(64),
      bytes: 100,
      days: 1,
      dates: ["2020-01-01"],
      counts: { all: 3, likely: 1, possible: 1, outside: 1 },
    },
  ],
};

describe("archive index", () => {
  it("accepts complete non-destructive counts", () => {
    expect(isArchiveManifest(manifest)).toBe(true);
    expect(
      isArchiveManifest({
        ...manifest,
        counts: { ...manifest.counts, all: 2 },
      }),
    ).toBe(false);
  });

  it("loads only a validated same-origin index", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => manifest,
    });

    const result = await fetchArchive(new AbortController().signal, fetcher, "/atlas/");

    expect(result.counts.all).toBe(3);
    expect(String(fetcher.mock.calls[0][0])).toBe("/atlas/data/archive.json");
  });
});
