import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { cloudRange, isCloud, loadCloud, type CloudManifest } from "./cloud";

function pointBytes(): ArrayBuffer {
  const bytes = new ArrayBuffer(12 + 2 * 13);
  const raw = new Uint8Array(bytes);
  raw.set(new TextEncoder().encode("ATLASPT1"));
  const view = new DataView(bytes);
  view.setUint32(8, 2, true);
  [1, 2, 3, 4, 5, 6].forEach((value, index) =>
    view.setFloat32(12 + index * 4, value, true),
  );
  raw.set([0, 2], 12 + 24);
  return bytes;
}

function manifest(bytes: ArrayBuffer): CloudManifest {
  const digest = createHash("sha256").update(Buffer.from(bytes)).digest("hex");
  return {
    schema_version: 1,
    source: "arxiv",
    model: "all-minilm",
    model_digest: "a".repeat(64),
    model_revision: "b".repeat(40),
    projection: "anchor-cosine-8-v1",
    point_bytes: 13,
    count: 2,
    counts: { likely: 1, possible: 0, outside: 1 },
    shards: [
      {
        month: "2020-01",
        source_sha256: "c".repeat(64),
        count: 2,
        counts: { likely: 1, possible: 0, outside: 1 },
        points: { path: "2020-01.bin", sha256: digest, bytes: bytes.byteLength },
        meta: { path: "2020-01.json", sha256: "d".repeat(64), bytes: 10 },
      },
    ],
  };
}

describe("paper cloud", () => {
  it("validates and decodes aligned fixed-width point shards", async () => {
    const bytes = pointBytes();
    const index = manifest(bytes);
    const fetcher = vi.fn(async () => new Response(bytes)) as unknown as typeof fetch;

    expect(isCloud(index)).toBe(true);
    const data = await loadCloud(
      index,
      new AbortController().signal,
      fetcher,
      "/atlas",
    );

    expect([...data.positions]).toEqual([1, 2, 3, 4, 5, 6]);
    expect([...data.scopes]).toEqual([0, 2]);
    expect(cloudRange(data, 1)?.month).toBe("2020-01");
    expect(cloudRange(data, 2)).toBeNull();
  });

  it("rejects inconsistent totals", () => {
    const index = manifest(pointBytes());
    index.count = 3;
    expect(isCloud(index)).toBe(false);
  });
});
