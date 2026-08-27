import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  createCloud,
  loadCloud,
  streamCloud,
  type CloudManifest,
  type CloudStep,
} from "./cloud";

type PointAsset = {
  bytes: ArrayBuffer;
  month: string;
  path: string;
};

type Deferred<Value> = {
  promise: Promise<Value>;
  resolve: (value: Value) => void;
};

function deferred<Value>(): Deferred<Value> {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function monthAt(index: number): string {
  const year = 2000 + Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

function pointBytes(start: number, count: number): ArrayBuffer {
  const bytes = new ArrayBuffer(12 + count * 13);
  const raw = new Uint8Array(bytes);
  raw.set(new TextEncoder().encode("ATLASPT1"));
  const view = new DataView(bytes);
  view.setUint32(8, count, true);
  for (let local = 0; local < count; local += 1) {
    const value = start + local;
    const offset = 12 + local * 12;
    view.setFloat32(offset, value, true);
    view.setFloat32(offset + 4, -value, true);
    view.setFloat32(offset + 8, value % 997, true);
    raw[12 + count * 12 + local] = 0;
  }
  return bytes;
}

function scaleCase(counts: readonly number[]): {
  assets: Map<string, PointAsset>;
  manifest: CloudManifest;
} {
  const assets = new Map<string, PointAsset>();
  let start = 0;
  const shards = counts.map((count, index) => {
    const month = monthAt(index);
    const path = `${month}.bin`;
    const bytes = pointBytes(start, count);
    const sha256 = createHash("sha256").update(Buffer.from(bytes)).digest("hex");
    assets.set(path, { bytes, month, path });
    start += count;
    return {
      month,
      source_sha256: "c".repeat(64),
      source_count: count,
      source_counts: { likely: count, possible: 0, outside: 0 },
      foreground_sha256: "f".repeat(64),
      count,
      counts: { likely: count, possible: 0, outside: 0 },
      omitted_count: 0,
      omitted_counts: { likely: 0, possible: 0, outside: 0 },
      omitted_ids: [],
      omitted_sha256: "e".repeat(64),
      points: { path, sha256, bytes: bytes.byteLength },
      meta: {
        path: `${month}.json`,
        sha256: "d".repeat(64),
        bytes: 1,
      },
    };
  });
  return {
    assets,
    manifest: {
      schema_version: 1,
      source: "arxiv",
      model: "all-minilm",
      model_digest: "a".repeat(64),
      model_revision: "b".repeat(40),
      projection: "anchor-cosine-8-v1",
      point_bytes: 13,
      source_count: start,
      count: start,
      counts: { likely: start, possible: 0, outside: 0 },
      omitted_count: 0,
      omitted_counts: { likely: 0, possible: 0, outside: 0 },
      omitted_sha256: "e".repeat(64),
      foreground_sha256: "f".repeat(64),
      shards,
    },
  };
}

function assetPath(input: RequestInfo | URL): string {
  const url = new URL(String(input), "https://atlas.test");
  return url.pathname.split("/").at(-1)!;
}

describe("paper cloud scale boundaries", () => {
  it("assembles one million points completely in manifest order", async () => {
    const { assets, manifest } = scaleCase(Array.from({ length: 20 }, () => 50_000));
    const requested: string[] = [];
    const steps: CloudStep[] = [];
    const observations: Array<{
      loaded: number;
      lastX: number;
      positions: ArrayBufferLike;
      scopes: ArrayBufferLike;
    }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const path = assetPath(input);
      requested.push(path);
      const asset = assets.get(path);
      return asset ? new Response(asset.bytes) : new Response(null, { status: 404 });
    }) as unknown as typeof fetch;

    const data = createCloud(manifest);
    const positions = data.positions.buffer;
    const scopes = data.scopes.buffer;
    const loaded = await streamCloud(
      manifest,
      data,
      new AbortController().signal,
      (step) => {
        steps.push(step);
        observations.push({
          loaded: data.loaded,
          lastX: data.positions[(step.loaded - 1) * 3],
          positions: data.positions.buffer,
          scopes: data.scopes.buffer,
        });
      },
      fetcher,
      "/atlas/",
    );

    expect(loaded).toBe(data);
    expect(data.positions.buffer).toBe(positions);
    expect(data.scopes.buffer).toBe(scopes);
    expect(data.loaded).toBe(1_000_000);
    expect(data.scopes).toHaveLength(1_000_000);
    expect(data.positions).toHaveLength(3_000_000);
    expect(data.ranges).toHaveLength(20);
    expect(
      data.ranges.map(({ month, start, count }) => ({ month, start, count })),
    ).toEqual(
      Array.from({ length: 20 }, (_, index) => ({
        month: monthAt(index),
        start: index * 50_000,
        count: 50_000,
      })),
    );
    expect([...data.positions.slice(0, 6)]).toEqual([0, -0, 0, 1, -1, 1]);
    expect([...data.positions.slice(-3)]).toEqual([999_999, -999_999, 999_999 % 997]);
    expect(data.scopes.every((scope) => scope === 0)).toBe(true);
    expect(data.radius).toBeGreaterThan(0);
    expect(steps).toEqual(
      Array.from({ length: 20 }, (_, index) => ({
        start: index * 50_000,
        count: 50_000,
        loaded: (index + 1) * 50_000,
        total: 1_000_000,
      })),
    );
    expect(observations.every((entry) => entry.positions === positions)).toBe(true);
    expect(observations.every((entry) => entry.scopes === scopes)).toBe(true);
    expect(observations.map(({ loaded, lastX }) => ({ loaded, lastX }))).toEqual(
      steps.map((step) => ({ loaded: step.loaded, lastX: step.loaded - 1 })),
    );
    expect(requested).toEqual(manifest.shards.map((shard) => shard.points.path));
    expect(requested.some((path) => path.endsWith(".json"))).toBe(false);
  }, 20_000);

  it("bounds concurrent shard requests and preserves order across out-of-order replies", async () => {
    const { assets, manifest } = scaleCase(Array.from({ length: 9 }, () => 2));
    let active = 0;
    let maximum = 0;
    const steps: CloudStep[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const asset = assets.get(assetPath(input));
      if (!asset) return new Response(null, { status: 404 });
      active += 1;
      maximum = Math.max(maximum, active);
      const index = Number(asset.month.slice(-2));
      await new Promise((resolve) => setTimeout(resolve, (10 - index) * 2));
      active -= 1;
      return new Response(asset.bytes);
    }) as unknown as typeof fetch;

    const data = createCloud(manifest);
    await streamCloud(
      manifest,
      data,
      new AbortController().signal,
      (step) => steps.push(step),
      fetcher,
    );

    expect(maximum).toBeLessThanOrEqual(4);
    expect(maximum).toBeGreaterThan(1);
    expect([...data.positions.filter((_, index) => index % 3 === 0)]).toEqual(
      Array.from({ length: 18 }, (_, index) => index),
    );
    expect(data.ranges.map((range) => range.month)).toEqual(
      manifest.shards.map((shard) => shard.month),
    );
    expect(steps.map((step) => step.start)).toEqual(
      Array.from({ length: 9 }, (_, index) => index * 2),
    );
    expect(steps.map((step) => step.loaded)).toEqual(
      Array.from({ length: 9 }, (_, index) => (index + 1) * 2),
    );
  });

  it("keeps all four worker slots busy while commits wait for manifest order", async () => {
    const { assets, manifest } = scaleCase(Array.from({ length: 9 }, () => 2));
    const gates = new Map(
      [...assets].map(([path, asset]) => [
        path,
        { asset, response: deferred<Response>() },
      ]),
    );
    const started: string[] = [];
    const steps: CloudStep[] = [];
    let active = 0;
    let maximum = 0;
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const path = assetPath(input);
      const gate = gates.get(path)!;
      started.push(path);
      active += 1;
      maximum = Math.max(maximum, active);
      return gate.response.promise.finally(() => {
        active -= 1;
      });
    }) as unknown as typeof fetch;
    const data = createCloud(manifest);
    const loading = streamCloud(
      manifest,
      data,
      new AbortController().signal,
      (step) => steps.push(step),
      fetcher,
    );
    await vi.waitFor(() => expect(started).toHaveLength(4));

    const fourth = manifest.shards[3].points.path;
    gates.get(fourth)!.response.resolve(new Response(gates.get(fourth)!.asset.bytes));
    await vi.waitFor(() => expect(started).toContain(manifest.shards[4].points.path));

    expect(active).toBe(4);
    expect(steps).toHaveLength(0);
    for (const shard of manifest.shards) {
      const gate = gates.get(shard.points.path)!;
      gate.response.resolve(new Response(gate.asset.bytes));
    }
    await loading;

    expect(maximum).toBe(4);
    expect(started).toHaveLength(9);
    expect(steps.map((step) => step.start)).toEqual(
      Array.from({ length: 9 }, (_, index) => index * 2),
    );
  });

  it("bounds decoded lookahead behind a stalled first shard", async () => {
    const { assets, manifest } = scaleCase(Array.from({ length: 12 }, () => 2));
    const gates = new Map(
      [...assets].map(([path, asset]) => [
        path,
        { asset, response: deferred<Response>() },
      ]),
    );
    const started: string[] = [];
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const path = assetPath(input);
      started.push(path);
      return gates.get(path)!.response.promise;
    }) as unknown as typeof fetch;
    const loading = streamCloud(
      manifest,
      createCloud(manifest),
      new AbortController().signal,
      undefined,
      fetcher,
    );
    await vi.waitFor(() => expect(started).toHaveLength(4));
    for (const shard of manifest.shards.slice(1, 4)) {
      const gate = gates.get(shard.points.path)!;
      gate.response.resolve(new Response(gate.asset.bytes));
    }
    await vi.waitFor(() => expect(started).toHaveLength(5));
    const fifth = gates.get(manifest.shards[4].points.path)!;
    fifth.response.resolve(new Response(fifth.asset.bytes));
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(started).toEqual(
      manifest.shards.slice(0, 5).map((shard) => shard.points.path),
    );

    for (const shard of manifest.shards) {
      const gate = gates.get(shard.points.path)!;
      gate.response.resolve(new Response(gate.asset.bytes));
    }
    await loading;
  });

  it("surfaces the shard failure that cancels earlier requests", async () => {
    const { assets, manifest } = scaleCase(Array.from({ length: 6 }, () => 2));
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = assetPath(input);
      if (path === manifest.shards[3].points.path) {
        return Promise.reject(new Error("fourth shard failed"));
      }
      const signal = init?.signal as AbortSignal;
      return new Promise<Response>((resolve, reject) => {
        const asset = assets.get(path)!;
        const timer = setTimeout(() => resolve(new Response(asset.bytes)), 50);
        signal.addEventListener(
          "abort",
          () => {
            clearTimeout(timer);
            reject(new DOMException("Aborted", "AbortError"));
          },
          { once: true },
        );
      });
    }) as unknown as typeof fetch;

    await expect(
      streamCloud(
        manifest,
        createCloud(manifest),
        new AbortController().signal,
        undefined,
        fetcher,
      ),
    ).rejects.toThrow("fourth shard failed");
  });

  it("fans cancellation into in-flight requests and starts no later shards", async () => {
    const { manifest } = scaleCase(Array.from({ length: 9 }, () => 2));
    const controller = new AbortController();
    const signals: AbortSignal[] = [];
    const started: string[] = [];
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      started.push(assetPath(input));
      const signal = init?.signal as AbortSignal;
      signals.push(signal);
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    }) as unknown as typeof fetch;

    const data = createCloud(manifest);
    const steps: CloudStep[] = [];
    const loading = streamCloud(
      manifest,
      data,
      controller.signal,
      (step) => {
        steps.push(step);
        controller.abort();
      },
      fetcher,
    );
    await Promise.resolve();
    expect(started).toHaveLength(4);

    // Abort before any response is available, while all four worker slots are busy.
    controller.abort();

    await expect(loading).rejects.toMatchObject({ name: "AbortError" });
    expect(signals).toHaveLength(4);
    expect(signals.every((signal) => signal === signals[0] && signal.aborted)).toBe(
      true,
    );
    expect(signals[0]).not.toBe(controller.signal);
    expect(started).toEqual(
      manifest.shards.slice(0, 4).map((shard) => shard.points.path),
    );
    expect(steps).toHaveLength(0);
    expect(data.loaded).toBe(0);
  });

  it("stops committing after cancellation from a progress callback", async () => {
    const { assets, manifest } = scaleCase(Array.from({ length: 6 }, () => 2));
    const controller = new AbortController();
    const steps: CloudStep[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const asset = assets.get(assetPath(input));
      if (!asset) return new Response(null, { status: 404 });
      await new Promise((resolve) => setTimeout(resolve, 2));
      return new Response(asset.bytes);
    }) as unknown as typeof fetch;
    const data = createCloud(manifest);

    const loading = streamCloud(
      manifest,
      data,
      controller.signal,
      (step) => {
        steps.push(step);
        controller.abort();
      },
      fetcher,
    );

    await expect(loading).rejects.toMatchObject({ name: "AbortError" });
    expect(steps).toEqual([{ start: 0, count: 2, loaded: 2, total: 12 }]);
    expect(data.loaded).toBe(2);
    expect([...data.positions.slice(0, 6)]).toEqual([0, -0, 0, 1, -1, 1]);
    expect(data.positions.slice(6).every((coordinate) => coordinate === 0)).toBe(true);
  });

  it("recovers cleanly when a fresh attempt follows a shard failure", async () => {
    const { assets, manifest } = scaleCase([2]);
    const asset = assets.get(manifest.shards[0].points.path)!;
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(new Response(asset.bytes)) as unknown as typeof fetch;

    await expect(
      loadCloud(manifest, new AbortController().signal, fetcher),
    ).rejects.toThrow("Paper point request failed (503)");

    const recovered = await loadCloud(manifest, new AbortController().signal, fetcher);
    expect([...recovered.positions]).toEqual([0, -0, 0, 1, -1, 1]);
    expect(recovered.ranges).toHaveLength(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
