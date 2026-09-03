import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  isPacks,
  loadPoint,
  packKey,
  pointUnits,
  type CloudPack,
  type PackAsset,
  type PackShard,
} from "./pack";

function packBytes(): ArrayBuffer {
  const bytes = new ArrayBuffer(12 + 3 * 13);
  const raw = new Uint8Array(bytes);
  raw.set(new TextEncoder().encode("ATLASPK1"));
  const view = new DataView(bytes);
  view.setUint32(8, 3, true);
  for (let index = 0; index < 9; index += 1) {
    view.setFloat32(12 + index * 4, index + 1, true);
  }
  raw.set([0, 1, 2], 12 + 36);
  return bytes;
}

function packCase(): {
  bytes: ArrayBuffer;
  pack: CloudPack;
  shards: PackShard[];
} {
  const bytes = packBytes();
  const pack: CloudPack = {
    months: ["1986-04", "1986-05"],
    count: 3,
    counts: { likely: 1, possible: 1, outside: 1 },
    points: {
      path: "p000.bin",
      sha256: createHash("sha256").update(Buffer.from(bytes)).digest("hex"),
      bytes: bytes.byteLength,
    },
  };
  const shards = [
    {
      month: "1986-04",
      count: 1,
      counts: { likely: 1, possible: 0, outside: 0 },
    },
    {
      month: "1986-05",
      count: 2,
      counts: { likely: 0, possible: 1, outside: 1 },
    },
  ];
  return { bytes, pack, shards };
}

function isAsset(value: unknown): value is PackAsset {
  const asset = value as Partial<PackAsset>;
  return (
    Boolean(value) &&
    typeof asset.path === "string" &&
    typeof asset.sha256 === "string" &&
    typeof asset.bytes === "number"
  );
}

describe("point packs", () => {
  it("uses stable fourteen-month calendar buckets", () => {
    expect(packKey("1986-04")).toBe(0);
    expect(packKey("1987-05")).toBe(0);
    expect(packKey("1987-06")).toBe(1);
    expect(packKey("1991-08")).toBe(4);
    expect(packKey("1986-03")).toBeNull();
  });

  it("validates exact month and lane coverage", () => {
    const { pack, shards } = packCase();

    expect(isPacks([pack], shards, isAsset)).toBe(true);
    expect(isPacks([{ ...pack, count: 2 }], shards, isAsset)).toBe(false);
    expect(
      isPacks([{ ...pack, months: [...pack.months].reverse() }], shards, isAsset),
    ).toBe(false);
    expect(
      isPacks(
        [{ ...pack, counts: { likely: 3, possible: 0, outside: 0 } }],
        shards,
        isAsset,
      ),
    ).toBe(false);
  });

  it("decodes one verified pack into one ordered load unit", async () => {
    const { bytes, pack, shards } = packCase();
    const units = pointUnits(shards, [pack]);
    const fetcher = vi.fn(async () => new Response(bytes));
    const digest = vi.fn(async () => pack.points.sha256);

    const loaded = await loadPoint(
      units[0],
      new AbortController().signal,
      fetcher as unknown as typeof fetch,
      "/data/cloud/p000.bin",
      digest,
    );

    expect(units).toHaveLength(1);
    expect(units[0].shards.map((shard) => shard.month)).toEqual(["1986-04", "1986-05"]);
    expect([...loaded.positions!]).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect([...loaded.scopes]).toEqual([0, 1, 2]);
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it("rejects digest, coordinate, and scope drift", async () => {
    const { bytes, pack, shards } = packCase();
    const unit = pointUnits(shards, [pack])[0];
    const fetcher = async () => new Response(bytes.slice(0));

    await expect(
      loadPoint(
        unit,
        new AbortController().signal,
        fetcher as unknown as typeof fetch,
        "/p000.bin",
        async () => "0".repeat(64),
      ),
    ).rejects.toThrow("digest");

    const invalid = bytes.slice(0);
    new DataView(invalid).setFloat32(12, Number.NaN, true);
    await expect(
      loadPoint(
        unit,
        new AbortController().signal,
        (async () => new Response(invalid)) as unknown as typeof fetch,
        "/p000.bin",
        async () => pack.points.sha256,
      ),
    ).rejects.toThrow("point pack is invalid");

    const scope = bytes.slice(0);
    new Uint8Array(scope)[scope.byteLength - 1] = 3;
    await expect(
      loadPoint(
        unit,
        new AbortController().signal,
        (async () => new Response(scope)) as unknown as typeof fetch,
        "/p000.bin",
        async () => pack.points.sha256,
      ),
    ).rejects.toThrow("point pack is invalid");
  });
});
