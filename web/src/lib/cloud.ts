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
  source_count: number;
  source_counts: { likely: number; possible: number; outside: number };
  foreground_sha256: string;
  count: number;
  counts: { likely: number; possible: number; outside: number };
  omitted_count: number;
  omitted_counts: { likely: number; possible: number; outside: number };
  omitted_ids: string[];
  omitted_sha256: string;
  points: CloudAsset;
  meta: CloudAsset;
  anchor_sha256?: string;
  row_sha256?: string;
  routes?: CloudAsset;
};

export type CloudManifest = {
  schema_version: 1;
  source: "arxiv";
  model: "all-minilm";
  model_digest: string;
  model_revision: string;
  projection: "anchor-cosine-8-v1";
  point_bytes: 13;
  relation?: "anchor-cosine-top8-v1";
  route_bytes?: 4;
  neighbor_count?: 8;
  anchor_count?: number;
  anchor_sha256?: string;
  anchors?: CloudAsset;
  source_count: number;
  count: number;
  counts: { likely: number; possible: number; outside: number };
  omitted_count: number;
  omitted_counts: { likely: number; possible: number; outside: number };
  omitted_sha256: string;
  foreground_sha256: string;
  shards: CloudShard[];
};

export type CloudRange = {
  month: string;
  start: number;
  count: number;
  meta: CloudAsset;
  anchor_sha256?: string;
  row_sha256?: string;
  routes?: CloudAsset;
};

export type CloudData = {
  positions: Float32Array;
  scopes: Uint8Array;
  ranges: CloudRange[];
  loaded: number;
  radius: number;
};

export type CloudStep = {
  start: number;
  count: number;
  loaded: number;
  total: number;
};

export type CloudPaper = {
  id: string;
  title: string;
  url: string;
  published: string;
  scope: "likely" | "possible" | "outside";
};

export type CloudPick = { index: number; paper: CloudPaper };

export type CloudRelation = {
  neighbors: { id: string; score: number }[];
};

const MONTH = /^\d{4}-\d{2}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const REVISION = /^[0-9a-f]{40}$/;
const POINT = /^\d{4}-\d{2}\.bin$/;
const META = /^\d{4}-\d{2}\.json$/;
const ROUTES = /^\d{4}-\d{2}\.routes$/;
const ANCHORS = /^anchors\.json$/;
const MAGIC = "ATLASPT1";
const CLOUD_WINDOW = 5;

export function cloudPath(asset: CloudAsset): string {
  return `/data/cloud/${asset.path}?sha=${asset.sha256}`;
}

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
  if (
    !isRecord(value) ||
    !isCounts(value.counts) ||
    !isCounts(value.source_counts) ||
    !isCounts(value.omitted_counts)
  ) {
    return false;
  }
  const sum = value.counts.likely + value.counts.possible + value.counts.outside;
  const sourceSum =
    value.source_counts.likely +
    value.source_counts.possible +
    value.source_counts.outside;
  const omittedSum =
    value.omitted_counts.likely +
    value.omitted_counts.possible +
    value.omitted_counts.outside;
  const omittedIds = Array.isArray(value.omitted_ids) ? value.omitted_ids : [];
  const routeCount = isCount(value.count) ? value.count : 0;
  const legacy =
    value.anchor_sha256 === undefined &&
    value.row_sha256 === undefined &&
    value.routes === undefined;
  const routed =
    isString(value.anchor_sha256) &&
    DIGEST.test(value.anchor_sha256) &&
    isString(value.row_sha256) &&
    DIGEST.test(value.row_sha256) &&
    isAsset(value.routes, ROUTES) &&
    value.routes.path === `${value.month}.routes` &&
    value.routes.bytes === 80 + routeCount * 8 * 4;
  return (
    isString(value.month) &&
    MONTH.test(value.month) &&
    isString(value.source_sha256) &&
    DIGEST.test(value.source_sha256) &&
    isCount(value.source_count) &&
    isString(value.foreground_sha256) &&
    DIGEST.test(value.foreground_sha256) &&
    isCount(value.count) &&
    value.count === sum &&
    isCount(value.omitted_count) &&
    value.omitted_count === omittedSum &&
    value.source_count === value.count + value.omitted_count &&
    value.source_count === sourceSum &&
    value.source_counts.likely === value.counts.likely + value.omitted_counts.likely &&
    value.source_counts.possible ===
      value.counts.possible + value.omitted_counts.possible &&
    value.source_counts.outside ===
      value.counts.outside + value.omitted_counts.outside &&
    omittedIds.length === value.omitted_count &&
    omittedIds.every(
      (identifier) =>
        isString(identifier) &&
        identifier.length > 0 &&
        identifier.length <= 128 &&
        !/\s/.test(identifier),
    ) &&
    omittedIds.join() === [...new Set(omittedIds)].sort().join() &&
    isString(value.omitted_sha256) &&
    DIGEST.test(value.omitted_sha256) &&
    isAsset(value.points, POINT) &&
    value.points.path === `${value.month}.bin` &&
    isAsset(value.meta, META) &&
    value.meta.path === `${value.month}.json` &&
    (legacy || routed)
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
    !isCount(value.source_count) ||
    !isCount(value.count) ||
    !isCounts(value.counts) ||
    !isCount(value.omitted_count) ||
    !isCounts(value.omitted_counts) ||
    !isString(value.omitted_sha256) ||
    !DIGEST.test(value.omitted_sha256) ||
    !isString(value.foreground_sha256) ||
    !DIGEST.test(value.foreground_sha256) ||
    !Array.isArray(value.shards) ||
    !value.shards.every(isShard)
  ) {
    return false;
  }
  const manifest = value as CloudManifest;
  const legacy =
    manifest.relation === undefined &&
    manifest.route_bytes === undefined &&
    manifest.neighbor_count === undefined &&
    manifest.anchor_count === undefined &&
    manifest.anchor_sha256 === undefined &&
    manifest.anchors === undefined;
  const routed =
    manifest.relation === "anchor-cosine-top8-v1" &&
    manifest.route_bytes === 4 &&
    manifest.neighbor_count === 8 &&
    isCount(manifest.anchor_count) &&
    manifest.anchor_count > 0 &&
    manifest.anchor_count <= 65_535 &&
    isString(manifest.anchor_sha256) &&
    DIGEST.test(manifest.anchor_sha256) &&
    isAsset(manifest.anchors, ANCHORS) &&
    manifest.anchors.path === "anchors.json" &&
    manifest.shards.every(
      (shard) =>
        shard.anchor_sha256 === manifest.anchor_sha256 && Boolean(shard.routes),
    );
  if (!legacy && !routed) return false;
  const months = manifest.shards.map((shard) => shard.month);
  if (months.join() !== [...new Set(months)].sort().join()) return false;
  const total = manifest.shards.reduce((sum, shard) => sum + shard.count, 0);
  const sourceTotal = manifest.shards.reduce(
    (sum, shard) => sum + shard.source_count,
    0,
  );
  const omittedTotal = manifest.shards.reduce(
    (sum, shard) => sum + shard.omitted_count,
    0,
  );
  const lanes = (["likely", "possible", "outside"] as const).every(
    (scope) =>
      manifest.counts[scope] ===
      manifest.shards.reduce((sum, shard) => sum + shard.counts[scope], 0),
  );
  const omittedLanes = (["likely", "possible", "outside"] as const).every(
    (scope) =>
      manifest.omitted_counts[scope] ===
      manifest.shards.reduce((sum, shard) => sum + shard.omitted_counts[scope], 0),
  );
  return (
    lanes &&
    omittedLanes &&
    manifest.count === total &&
    manifest.source_count === sourceTotal &&
    manifest.omitted_count === omittedTotal &&
    manifest.source_count === manifest.count + manifest.omitted_count &&
    manifest.count ===
      manifest.counts.likely + manifest.counts.possible + manifest.counts.outside &&
    manifest.omitted_count ===
      manifest.omitted_counts.likely +
        manifest.omitted_counts.possible +
        manifest.omitted_counts.outside
  );
}

export async function digestOf(bytes: ArrayBuffer): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

async function metaBytes(
  range: CloudRange,
  signal: AbortSignal,
  fetcher: typeof fetch,
  base?: string,
  reload = false,
): Promise<ArrayBuffer> {
  try {
    const response = await fetcher(basePath(cloudPath(range.meta), base), {
      signal,
      cache: reload ? "reload" : "force-cache",
    });
    if (!response.ok) {
      throw new Error(`Metadata request failed (${response.status})`);
    }
    const bytes = await response.arrayBuffer();
    if (
      bytes.byteLength !== range.meta.bytes ||
      (await digestOf(bytes)) !== range.meta.sha256
    ) {
      throw new Error("Metadata does not match its index");
    }
    return bytes;
  } catch (error) {
    if (reload || signal.aborted || (error as Error).name === "AbortError") {
      throw error;
    }
    return metaBytes(range, signal, fetcher, base, true);
  }
}

export async function fetchCloudMeta(
  range: CloudRange,
  signal: AbortSignal,
  scopes?: Uint8Array,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<CloudPaper[]> {
  const bytes = await metaBytes(range, signal, fetcher, base);
  const { parseRows } = await import("./cloudrow");
  return parseRows(bytes, range, scopes);
}

export function cloudPaper(
  papers: readonly CloudPaper[],
  range: CloudRange,
  index: number,
): CloudPaper | null {
  const local = index - range.start;
  if (local < 0 || local >= range.count) return null;
  return papers[local] ?? null;
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
): Promise<{ positions: Float32Array; scopes: Uint8Array; radius: number }> {
  const response = await fetcher(basePath(cloudPath(shard.points), base), {
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
  let radius = 0;
  for (let index = 0; index < count * 3; index += 1) {
    const coordinate = view.getFloat32(12 + index * 4, true);
    if (!Number.isFinite(coordinate)) {
      throw new Error("Paper point shard is invalid");
    }
    positions[index] = coordinate;
  }
  for (let index = 0; index < count; index += 1) {
    const offset = index * 3;
    radius = Math.max(
      radius,
      Math.hypot(positions[offset], positions[offset + 1], positions[offset + 2]),
    );
  }
  const scopes = new Uint8Array(bytes.slice(12 + count * 12));
  const scopeCounts = [0, 0, 0];
  for (const scope of scopes) {
    if (scope > 2) throw new Error("Paper point shard is invalid");
    scopeCounts[scope] += 1;
  }
  if (
    scopeCounts[0] !== shard.counts.likely ||
    scopeCounts[1] !== shard.counts.possible ||
    scopeCounts[2] !== shard.counts.outside
  ) {
    throw new Error("Paper point shard is invalid");
  }
  return { positions, scopes, radius };
}

export function createCloud(manifest: CloudManifest): CloudData {
  return {
    positions: new Float32Array(manifest.count * 3),
    scopes: new Uint8Array(manifest.count),
    ranges: [],
    loaded: 0,
    radius: 0,
  };
}

type ShardData = Awaited<ReturnType<typeof pointShard>>;
type ShardResult = { ok: true; data: ShardData } | { ok: false; error: unknown };

function abortLoad(signal: AbortSignal): void {
  if (!signal.aborted) return;
  throw signal.reason ?? new DOMException("Aborted", "AbortError");
}

export async function streamCloud(
  manifest: CloudManifest,
  data: CloudData,
  signal: AbortSignal,
  onStep?: (step: CloudStep) => void,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<CloudData> {
  abortLoad(signal);
  if (
    data.positions.length !== manifest.count * 3 ||
    data.scopes.length !== manifest.count ||
    data.loaded !== 0 ||
    data.ranges.length !== 0
  ) {
    throw new Error("Paper cloud target has an invalid shape");
  }
  const controller = new AbortController();
  const forward = () => controller.abort(signal.reason);
  signal.addEventListener("abort", forward, { once: true });
  const results: (Promise<ShardResult> | undefined)[] = [];
  const settles: (((result: ShardResult) => void) | undefined)[] = [];
  for (const _shard of manifest.shards) {
    results.push(
      new Promise((resolve) => {
        settles.push(resolve);
      }),
    );
  }
  let next = 0;
  let committed = 0;
  let stopped = false;
  let failed = false;
  let failure: unknown;
  let windows: (() => void)[] = [];
  const wake = () => {
    const ready = windows;
    windows = [];
    ready.forEach((resolve) => resolve());
  };
  const waitSlot = async () => {
    while (!stopped && next - committed >= CLOUD_WINDOW) {
      await new Promise<void>((resolve) => windows.push(resolve));
    }
  };
  const work = async () => {
    while (!stopped) {
      await waitSlot();
      if (stopped || next >= manifest.shards.length) return;
      const index = next++;
      const shard = manifest.shards[index];
      const result: ShardResult = await pointShard(
        shard,
        controller.signal,
        fetcher,
        base,
      ).then(
        (loaded) => ({ ok: true, data: loaded }),
        (error: unknown) => ({ ok: false, error }),
      );
      settles[index]!(result);
      settles[index] = undefined;
      if (!result.ok || signal.aborted) {
        if (!result.ok && !controller.signal.aborted) {
          failed = true;
          failure = result.error;
        }
        stopped = true;
        controller.abort(result.ok ? signal.reason : result.error);
        wake();
      }
    }
  };
  const workers = Array.from({ length: Math.min(4, manifest.shards.length) }, () =>
    work(),
  );
  try {
    for (let index = 0; index < manifest.shards.length; index += 1) {
      const result = await results[index]!;
      results[index] = undefined;
      abortLoad(signal);
      if (!result.ok) throw failed ? failure : result.error;
      const loaded = result.data;
      const shard = manifest.shards[index];
      const start = data.loaded;
      data.positions.set(loaded.positions, start * 3);
      data.scopes.set(loaded.scopes, start);
      data.ranges.push({
        month: shard.month,
        start,
        count: loaded.scopes.length,
        meta: shard.meta,
        anchor_sha256: shard.anchor_sha256,
        row_sha256: shard.row_sha256,
        routes: shard.routes,
      });
      data.loaded += loaded.scopes.length;
      data.radius = Math.max(data.radius, loaded.radius);
      onStep?.({
        start,
        count: loaded.scopes.length,
        loaded: data.loaded,
        total: manifest.count,
      });
      abortLoad(signal);
      committed = index + 1;
      wake();
    }
    await Promise.all(workers);
    if (data.loaded !== manifest.count) {
      throw new Error("Paper cloud count drifted while loading");
    }
    return data;
  } finally {
    stopped = true;
    controller.abort();
    signal.removeEventListener("abort", forward);
    wake();
    void Promise.all(workers);
  }
}

export async function loadCloud(
  manifest: CloudManifest,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<CloudData> {
  const data = createCloud(manifest);
  return streamCloud(manifest, data, signal, undefined, fetcher, base);
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
