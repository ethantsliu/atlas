import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  cloudPaper,
  cloudRange,
  createCloud,
  fetchCloudMeta,
  isCloud,
  loadCloud,
  streamCloud,
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

function metaCase() {
  const bytes = new TextEncoder().encode(
    JSON.stringify({
      schema_version: 1,
      month: "2020-01",
      count: 1,
      papers: [
        [
          "2001.00001",
          "First",
          "https://arxiv.org/abs/2001.00001",
          "2020-01-02",
          "likely",
        ],
      ],
    }),
  );
  const range: CloudRange = {
    month: "2020-01",
    start: 0,
    count: 1,
    meta: {
      path: "2020-01.json",
      sha256: createHash("sha256").update(bytes).digest("hex"),
      bytes: bytes.byteLength,
    },
  };
  return { bytes, range };
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

function packBytes(parts: ArrayBuffer[]): ArrayBuffer {
  const counts = parts.map((part) => new DataView(part).getUint32(8, true));
  const count = counts.reduce((sum, value) => sum + value, 0);
  const bytes = new ArrayBuffer(12 + count * 13);
  const raw = new Uint8Array(bytes);
  raw.set(new TextEncoder().encode("ATLASPK1"));
  new DataView(bytes).setUint32(8, count, true);
  let pointAt = 12;
  let scopeAt = 12 + count * 12;
  parts.forEach((part, index) => {
    const local = counts[index];
    raw.set(new Uint8Array(part, 12, local * 12), pointAt);
    raw.set(new Uint8Array(part, 12 + local * 12, local), scopeAt);
    pointAt += local * 12;
    scopeAt += local;
  });
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

  it("commits concurrent shard responses in manifest order", async () => {
    const first = pointBytes();
    const second = pointBytes(7);
    const index = manifest(first);
    const next = structuredClone(index.shards[0]);
    next.month = "2020-02";
    next.points = {
      path: "2020-02.bin",
      sha256: createHash("sha256").update(Buffer.from(second)).digest("hex"),
      bytes: second.byteLength,
    };
    next.meta = { ...next.meta, path: "2020-02.json" };
    index.shards.push(next);
    index.source_count = 6;
    index.count = 4;
    index.counts = { likely: 2, possible: 0, outside: 2 };
    index.omitted_count = 2;
    index.omitted_counts = { likely: 0, possible: 2, outside: 0 };
    expect(isCloud(index)).toBe(true);
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const responses: string[] = [];
    const request = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("2020-01")) await gate;
      else release();
      responses.push(url);
      return new Response(url.includes("2020-01") ? first : second);
    });
    const steps: number[] = [];

    const data = await streamCloud(
      index,
      createCloud(index),
      new AbortController().signal,
      (step) => steps.push(step.start),
      request as unknown as typeof fetch,
    );

    expect(responses[0]).toContain("2020-02");
    expect(steps).toEqual([0, 2]);
    expect(data.ranges.map((range) => range.month)).toEqual(["2020-01", "2020-02"]);
    expect([...data.positions]).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    expect([...data.scopes]).toEqual([0, 2, 0, 2]);
  });

  it("prefers one verified point pack while retaining monthly ranges", async () => {
    const first = pointBytes();
    const second = pointBytes(7);
    const packed = packBytes([first, second]);
    const index = manifest(first);
    const next = structuredClone(index.shards[0]);
    next.month = "2020-02";
    next.points = {
      path: "2020-02.bin",
      sha256: createHash("sha256").update(Buffer.from(second)).digest("hex"),
      bytes: second.byteLength,
    };
    next.meta = { ...next.meta, path: "2020-02.json" };
    index.shards.push(next);
    index.source_count = 6;
    index.count = 4;
    index.counts = { likely: 2, possible: 0, outside: 2 };
    index.omitted_count = 2;
    index.omitted_counts = { likely: 0, possible: 2, outside: 0 };
    index.point_pack = "month-14-v1";
    index.pack_months = 14;
    index.packs = [
      {
        months: ["2020-01", "2020-02"],
        count: 4,
        counts: { likely: 2, possible: 0, outside: 2 },
        points: {
          path: "p024.bin",
          sha256: createHash("sha256").update(Buffer.from(packed)).digest("hex"),
          bytes: packed.byteLength,
        },
      },
    ];
    const request = vi.fn(async (_input: RequestInfo | URL) => new Response(packed));
    const steps: number[] = [];

    expect(isCloud(index)).toBe(true);
    const data = await streamCloud(
      index,
      createCloud(index),
      new AbortController().signal,
      (step) => steps.push(step.loaded),
      request as unknown as typeof fetch,
    );

    expect(request).toHaveBeenCalledOnce();
    expect(String(request.mock.calls[0][0])).toContain("p024.bin");
    expect(data.ranges.map((range) => range.month)).toEqual(["2020-01", "2020-02"]);
    expect(data.ranges.map((range) => range.start)).toEqual([0, 2]);
    expect([...data.positions]).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    expect([...data.scopes]).toEqual([0, 2, 0, 2]);
    expect(steps).toEqual([4]);

    delete index.packs;
    expect(isCloud(index)).toBe(false);
  });

  it("rejects inconsistent totals", () => {
    const index = manifest(pointBytes());
    index.count = 3;
    expect(isCloud(index)).toBe(false);
  });

  it("rejects non-finite coordinates and scope count drift", async () => {
    const invalidPoint = pointBytes();
    new DataView(invalidPoint).setFloat32(12, Number.NaN, true);
    await expect(
      loadCloud(
        manifest(invalidPoint),
        new AbortController().signal,
        (async () => new Response(invalidPoint)) as unknown as typeof fetch,
      ),
    ).rejects.toThrow("point shard is invalid");

    const invalidScopes = pointBytes();
    new Uint8Array(invalidScopes)[12 + 24 + 1] = 1;
    await expect(
      loadCloud(
        manifest(invalidScopes),
        new AbortController().signal,
        (async () => new Response(invalidScopes)) as unknown as typeof fetch,
      ),
    ).rejects.toThrow("point shard is invalid");
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
      row_sha256: createHash("sha256")
        .update(JSON.stringify(["2001.00001", "2001.00002"]))
        .digest("hex"),
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
      new Uint8Array([0, 2]),
      fetcher,
      "/atlas",
    );

    expect(cloudPaper(papers, range, 11)?.title).toBe("Second");
    expect(cloudPaper(papers, range, 12)).toBeNull();
    expect(String(request.mock.calls[0][0])).toBe(
      `/atlas/data/cloud/2020-01.json?sha=${range.meta.sha256}`,
    );
    expect(request).toHaveBeenCalledTimes(1);

    await expect(
      fetchCloudMeta(
        range,
        new AbortController().signal,
        new Uint8Array([2, 0]),
        fetcher,
      ),
    ).rejects.toThrow("invalid shape");
  });

  it("retries one transient metadata mismatch without trusting it", async () => {
    const { bytes, range } = metaCase();
    const request = vi
      .fn()
      .mockResolvedValueOnce(new Response("<!doctype html>"))
      .mockResolvedValueOnce(new Response(bytes));

    const papers = await fetchCloudMeta(
      range,
      new AbortController().signal,
      new Uint8Array([0]),
      request as unknown as typeof fetch,
    );

    expect(papers[0].title).toBe("First");
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[1][1]).toMatchObject({ cache: "reload" });
  });

  it("never retries an aborted metadata request", async () => {
    const { range } = metaCase();
    const request = vi.fn(async () => {
      throw new DOMException("Aborted", "AbortError");
    });

    await expect(
      fetchCloudMeta(
        range,
        new AbortController().signal,
        new Uint8Array([0]),
        request as unknown as typeof fetch,
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(request).toHaveBeenCalledOnce();
  });

  it("rejects metadata row identity drift", async () => {
    const meta = new TextEncoder().encode(
      JSON.stringify({
        schema_version: 1,
        month: "2020-01",
        count: 1,
        papers: [
          [
            "2001.00001",
            "First",
            "https://arxiv.org/abs/2001.00001",
            "2020-01-02",
            "likely",
          ],
        ],
      }),
    );
    const range: CloudRange = {
      month: "2020-01",
      start: 0,
      count: 1,
      row_sha256: "f".repeat(64),
      meta: {
        path: "2020-01.json",
        sha256: createHash("sha256").update(meta).digest("hex"),
        bytes: meta.byteLength,
      },
    };
    await expect(
      fetchCloudMeta(
        range,
        new AbortController().signal,
        undefined,
        (async () => new Response(meta)) as unknown as typeof fetch,
      ),
    ).rejects.toThrow("row identity");
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
