import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  cloudPaper,
  cloudRange,
  fetchCloudMeta,
  isCloud,
  loadCloud,
  type CloudManifest,
  type CloudRange,
} from "./cloud";
import { fetchRelation } from "./relation";

function hexInto(bytes: ArrayBuffer, offset: number, value: string) {
  new Uint8Array(bytes, offset, 32).set(Buffer.from(value, "hex"));
}

function routeBytes(anchor: string, row: string): ArrayBuffer {
  const bytes = new ArrayBuffer(80 + 2 * 8 * 4);
  const raw = new Uint8Array(bytes);
  raw.set(new TextEncoder().encode("ATLASRT1"));
  const view = new DataView(bytes);
  view.setUint32(8, 2, true);
  view.setUint16(12, 8, true);
  view.setUint16(14, 8, true);
  hexInto(bytes, 16, row);
  hexInto(bytes, 48, anchor);
  for (let paper = 0; paper < 2; paper += 1) {
    for (let slot = 0; slot < 8; slot += 1) {
      const offset = 80 + (paper * 8 + slot) * 4;
      view.setUint16(offset, slot, true);
      view.setUint16(offset + 2, 65_535 - slot, true);
    }
  }
  return bytes;
}

function pointBytes(start = 1): ArrayBuffer {
  const bytes = new ArrayBuffer(12 + 2 * 13);
  const raw = new Uint8Array(bytes);
  raw.set(new TextEncoder().encode("ATLASPT1"));
  const view = new DataView(bytes);
  view.setUint32(8, 2, true);
  Array.from({ length: 6 }, (_, index) => start + index).forEach((value, index) =>
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
    source_count: 3,
    count: 2,
    counts: { likely: 1, possible: 0, outside: 1 },
    omitted_count: 1,
    omitted_counts: { likely: 0, possible: 1, outside: 0 },
    omitted_sha256: "e".repeat(64),
    foreground_sha256: "f".repeat(64),
    shards: [
      {
        month: "2020-01",
        source_sha256: "c".repeat(64),
        source_count: 3,
        source_counts: { likely: 1, possible: 1, outside: 1 },
        foreground_sha256: "f".repeat(64),
        count: 2,
        counts: { likely: 1, possible: 0, outside: 1 },
        omitted_count: 1,
        omitted_counts: { likely: 0, possible: 1, outside: 0 },
        omitted_ids: ["2001.00003"],
        omitted_sha256: "e".repeat(64),
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
    const request = vi.fn(async (_input: RequestInfo | URL) => new Response(bytes));
    const fetcher = request as unknown as typeof fetch;

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
    expect(String(request.mock.calls[0][0])).toBe(
      `/atlas/data/cloud/2020-01.bin?sha=${index.shards[0].points.sha256}`,
    );
  });

  it("keys mutable shard paths by the manifest digest across updates", async () => {
    const first = pointBytes();
    const second = pointBytes(7);
    const firstIndex = manifest(first);
    const secondIndex = manifest(second);
    const assets = new Map([
      [firstIndex.shards[0].points.sha256, first],
      [secondIndex.shards[0].points.sha256, second],
    ]);
    const cache = new Map<string, ArrayBuffer>();
    const request = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let content = cache.get(url);
      if (!content) {
        const digest = new URL(url, "https://atlas.test").searchParams.get("sha");
        content = digest ? assets.get(digest) : undefined;
        if (!content) return new Response(null, { status: 404 });
        cache.set(url, content);
      }
      return new Response(content);
    });
    const fetcher = request as unknown as typeof fetch;

    const oldData = await loadCloud(
      firstIndex,
      new AbortController().signal,
      fetcher,
      "/atlas",
    );
    const newData = await loadCloud(
      secondIndex,
      new AbortController().signal,
      fetcher,
      "/atlas",
    );

    expect(oldData.positions[0]).toBe(1);
    expect(newData.positions[0]).toBe(7);
    expect(request.mock.calls.map((call) => String(call[0]))).toEqual([
      `/atlas/data/cloud/2020-01.bin?sha=${firstIndex.shards[0].points.sha256}`,
      `/atlas/data/cloud/2020-01.bin?sha=${secondIndex.shards[0].points.sha256}`,
    ]);
  });

  it("rejects inconsistent totals", () => {
    const index = manifest(pointBytes());
    index.count = 3;
    expect(isCloud(index)).toBe(false);
  });

  it("lazily validates metadata and resolves an aligned point", async () => {
    const meta = new TextEncoder().encode(
      JSON.stringify({
        schema_version: 1,
        month: "2020-01",
        count: 2,
        papers: [
          [
            "2001.00001",
            "First",
            "https://arxiv.org/abs/2001.00001",
            "2020-01-02",
            "likely",
          ],
          [
            "2001.00002",
            "Second",
            "https://arxiv.org/abs/2001.00002",
            "2020-01-03",
            "outside",
          ],
        ],
      }),
    );
    const range: CloudRange = {
      month: "2020-01",
      start: 10,
      count: 2,
      meta: {
        path: "2020-01.json",
        sha256: createHash("sha256").update(meta).digest("hex"),
        bytes: meta.byteLength,
      },
    };
    const request = vi.fn(async (_input: RequestInfo | URL) => new Response(meta));
    const fetcher = request as unknown as typeof fetch;

    const papers = await fetchCloudMeta(
      range,
      new AbortController().signal,
      fetcher,
      "/atlas",
    );

    expect(cloudPaper(papers, range, 11)?.title).toBe("Second");
    expect(cloudPaper(papers, range, 12)).toBeNull();
    expect(String(request.mock.calls[0][0])).toBe(
      `/atlas/data/cloud/2020-01.json?sha=${range.meta.sha256}`,
    );
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("loads one aligned exact-cosine anchor route", async () => {
    const anchorSha = "a".repeat(64);
    const rowSha = "b".repeat(64);
    const ids = Array.from({ length: 8 }, (_, index) => `topic:anchor-${index}`);
    const anchorBytes = new TextEncoder().encode(
      JSON.stringify({
        schema_version: 1,
        model: "all-minilm",
        model_digest: "a".repeat(64),
        anchor_sha256: anchorSha,
        count: ids.length,
        ids,
      }),
    );
    const routes = routeBytes(anchorSha, rowSha);
    const index = manifest(pointBytes());
    index.relation = "anchor-cosine-top8-v1";
    index.route_bytes = 4;
    index.neighbor_count = 8;
    index.anchor_count = 8;
    index.anchor_sha256 = anchorSha;
    index.anchors = {
      path: "anchors.json",
      sha256: createHash("sha256").update(anchorBytes).digest("hex"),
      bytes: anchorBytes.byteLength,
    };
    index.shards[0].anchor_sha256 = anchorSha;
    index.shards[0].row_sha256 = rowSha;
    index.shards[0].routes = {
      path: "2020-01.routes",
      sha256: createHash("sha256").update(Buffer.from(routes)).digest("hex"),
      bytes: routes.byteLength,
    };
    const range: CloudRange = {
      month: "2020-01",
      start: 0,
      count: 2,
      meta: index.shards[0].meta,
      anchor_sha256: anchorSha,
      row_sha256: rowSha,
      routes: index.shards[0].routes,
    };
    const request = vi.fn(
      async (input: RequestInfo | URL) =>
        new Response(String(input).includes("anchors.json") ? anchorBytes : routes),
    );

    expect(isCloud(index)).toBe(true);
    const relation = await fetchRelation(
      index,
      range,
      1,
      new AbortController().signal,
      request as unknown as typeof fetch,
      "/atlas",
    );

    expect(relation.neighbors.map((neighbor) => neighbor.id)).toEqual(ids);
    expect(relation.neighbors[0].score).toBe(1);
    expect(relation.neighbors[7].score).toBeLessThan(1);
    expect(request).toHaveBeenCalledTimes(2);
  });
});
