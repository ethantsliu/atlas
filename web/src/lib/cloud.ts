import { isNumber, isRecord, isString } from "./guards";
import { basePath } from "./paths";

export type CloudAsset = {
  path: string;
  sha256: string;
  bytes: number;
};

export type CloudShard = {
  month: string;
  source_sha256: string;
  count: number;
  counts: { likely: number; possible: number; outside: number };
  points: CloudAsset;
  meta: CloudAsset;
};

export type CloudManifest = {
  schema_version: 1;
  source: "arxiv";
  model: "all-minilm";
  model_digest: string;
  model_revision: string;
  projection: "anchor-cosine-8-v1";
  point_bytes: 13;
  count: number;
  counts: { likely: number; possible: number; outside: number };
  shards: CloudShard[];
};

export type CloudRange = {
  month: string;
  start: number;
  count: number;
  meta: CloudAsset;
};

export type CloudData = {
  positions: Float32Array;
  scopes: Uint8Array;
  ranges: CloudRange[];
};

export type CloudPaper = {
  id: string;
  title: string;
  url: string;
  published: string;
  scope: "likely" | "possible" | "outside";
};

const MONTH = /^\d{4}-\d{2}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const REVISION = /^[0-9a-f]{40}$/;
const POINT = /^\d{4}-\d{2}\.bin$/;
const META = /^\d{4}-\d{2}\.json$/;
const MAGIC = "ATLASPT1";

function isCount(value: unknown): value is number {
  return isNumber(value) && Number.isSafeInteger(value) && value >= 0;
}

function isAsset(value: unknown, pattern: RegExp): value is CloudAsset {
  if (!isRecord(value)) return false;
  return (
    isString(value.path) &&
    pattern.test(value.path) &&
    isString(value.sha256) &&
    DIGEST.test(value.sha256) &&
    isCount(value.bytes) &&
    value.bytes > 0
  );
}

function isCounts(value: unknown): value is CloudShard["counts"] {
  if (!isRecord(value)) return false;
  return isCount(value.likely) && isCount(value.possible) && isCount(value.outside);
}

function isShard(value: unknown): value is CloudShard {
  if (!isRecord(value) || !isCounts(value.counts)) return false;
  const sum = value.counts.likely + value.counts.possible + value.counts.outside;
  return (
    isString(value.month) &&
    MONTH.test(value.month) &&
    isString(value.source_sha256) &&
    DIGEST.test(value.source_sha256) &&
    isCount(value.count) &&
    value.count === sum &&
    isAsset(value.points, POINT) &&
    value.points.path === `${value.month}.bin` &&
    isAsset(value.meta, META) &&
    value.meta.path === `${value.month}.json`
  );
}

export function isCloud(value: unknown): value is CloudManifest {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    value.source !== "arxiv" ||
    value.model !== "all-minilm" ||
    !isString(value.model_digest) ||
    !DIGEST.test(value.model_digest) ||
    !isString(value.model_revision) ||
    !REVISION.test(value.model_revision) ||
    value.projection !== "anchor-cosine-8-v1" ||
    value.point_bytes !== 13 ||
    !isCount(value.count) ||
    !isCounts(value.counts) ||
    !Array.isArray(value.shards) ||
    !value.shards.every(isShard)
  ) {
    return false;
  }
  const manifest = value as CloudManifest;
  const months = manifest.shards.map((shard) => shard.month);
  if (months.join() !== [...new Set(months)].sort().join()) return false;
  const total = manifest.shards.reduce((sum, shard) => sum + shard.count, 0);
  const lanes = (["likely", "possible", "outside"] as const).every(
    (scope) =>
      manifest.counts[scope] ===
      manifest.shards.reduce((sum, shard) => sum + shard.counts[scope], 0),
  );
  return (
    lanes &&
    manifest.count === total &&
    manifest.count ===
      manifest.counts.likely + manifest.counts.possible + manifest.counts.outside
  );
}

async function digestOf(bytes: ArrayBuffer): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export async function fetchCloud(
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<CloudManifest> {
  const response = await fetcher(basePath("/data/cloud/index.json", base), {
    signal,
    cache: "no-cache",
  });
  if (!response.ok) throw new Error(`Paper cloud request failed (${response.status})`);
  const value: unknown = await response.json();
  if (!isCloud(value)) throw new Error("Paper cloud index has an invalid shape");
  return value;
}

async function pointShard(
  shard: CloudShard,
  signal: AbortSignal,
  fetcher: typeof fetch,
  base?: string,
): Promise<{ positions: Float32Array; scopes: Uint8Array }> {
  const response = await fetcher(basePath(`/data/cloud/${shard.points.path}`, base), {
    signal,
    cache: "force-cache",
  });
  if (!response.ok) throw new Error(`Paper point request failed (${response.status})`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== shard.points.bytes) {
    throw new Error("Paper point byte length does not match its index");
  }
  if ((await digestOf(bytes)) !== shard.points.sha256) {
    throw new Error("Paper point digest does not match its index");
  }
  const view = new DataView(bytes);
  const magic = new TextDecoder().decode(new Uint8Array(bytes, 0, 8));
  const count = view.getUint32(8, true);
  if (
    magic !== MAGIC ||
    count !== shard.count ||
    bytes.byteLength !== 12 + count * 13
  ) {
    throw new Error("Paper point shard has an invalid contract");
  }
  const positions = new Float32Array(count * 3);
  for (let index = 0; index < count * 3; index += 1) {
    positions[index] = view.getFloat32(12 + index * 4, true);
  }
  const scopes = new Uint8Array(bytes.slice(12 + count * 12));
  if (scopes.some((scope) => scope > 2)) {
    throw new Error("Paper point shard contains an invalid scope");
  }
  return { positions, scopes };
}

export async function loadCloud(
  manifest: CloudManifest,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<CloudData> {
  const positions = new Float32Array(manifest.count * 3);
  const scopes = new Uint8Array(manifest.count);
  const ranges: CloudRange[] = [];
  let next = 0;
  for (let start = 0; start < manifest.shards.length; start += 4) {
    const shards = manifest.shards.slice(start, start + 4);
    const loaded = await Promise.all(
      shards.map((shard) => pointShard(shard, signal, fetcher, base)),
    );
    for (const [index, shard] of shards.entries()) {
      const data = loaded[index];
      positions.set(data.positions, next * 3);
      scopes.set(data.scopes, next);
      ranges.push({
        month: shard.month,
        start: next,
        count: shard.count,
        meta: shard.meta,
      });
      next += shard.count;
    }
  }
  return { positions, scopes, ranges };
}

export function cloudRange(data: CloudData, index: number): CloudRange | null {
  let low = 0;
  let high = data.ranges.length - 1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    const range = data.ranges[middle];
    if (index < range.start) high = middle - 1;
    else if (index >= range.start + range.count) low = middle + 1;
    else return range;
  }
  return null;
}
