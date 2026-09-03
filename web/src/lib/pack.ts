export type PackAsset = {
  path: string;
  sha256: string;
  bytes: number;
};

export type PackCounts = { likely: number; possible: number; outside: number };

export type PackShard = {
  month: string;
  count: number;
  counts: PackCounts;
};

export type CloudPack = {
  months: string[];
  count: number;
  counts: PackCounts;
  points: PackAsset;
};

export type PointUnit<Shard extends PackShard = PackShard> = {
  count: number;
  counts: PackCounts;
  magic: "ATLASPT1" | "ATLASPK1";
  points: PackAsset;
  shards: Shard[];
};

export type PointData = {
  count: number;
  positions: Float32Array | null;
  radius: number;
  scopes: Uint8Array;
  view: DataView;
};

type AssetCheck = (value: unknown) => value is PackAsset;
type Digest = (bytes: ArrayBuffer) => Promise<string>;

export const PACK_MODE = "month-14-v1";
export const PACK_MONTHS = 14;
const EPOCH = 1986 * 12 + 3;
const PATH = /^p\d{3,}\.bin$/;
const LITTLE_ENDIAN = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;

function monthOrd(month: string): number | null {
  if (!/^\d{4}-\d{2}$/.test(month)) return null;
  const year = Number(month.slice(0, 4));
  const number = Number(month.slice(5));
  if (!Number.isSafeInteger(year) || !Number.isSafeInteger(number)) return null;
  if (number < 1 || number > 12) return null;
  return year * 12 + number - 1;
}

export function packKey(month: string): number | null {
  const ordinal = monthOrd(month);
  if (ordinal == null || ordinal < EPOCH) return null;
  return Math.floor((ordinal - EPOCH) / PACK_MONTHS);
}

function packPath(key: number): string {
  return `p${String(key).padStart(3, "0")}.bin`;
}

function sameCounts(left: PackCounts, right: PackCounts): boolean {
  return (
    left.likely === right.likely &&
    left.possible === right.possible &&
    left.outside === right.outside
  );
}

function sumCounts(shards: readonly PackShard[]): PackCounts {
  return shards.reduce(
    (sum, shard) => ({
      likely: sum.likely + shard.counts.likely,
      possible: sum.possible + shard.counts.possible,
      outside: sum.outside + shard.counts.outside,
    }),
    { likely: 0, possible: 0, outside: 0 },
  );
}

function isCounts(value: unknown): value is PackCounts {
  if (!value || typeof value !== "object") return false;
  const counts = value as Partial<PackCounts>;
  return [counts.likely, counts.possible, counts.outside].every(
    (count) => typeof count === "number" && Number.isSafeInteger(count) && count >= 0,
  );
}

export function isPacks(
  value: unknown,
  shards: readonly PackShard[],
  isAsset: AssetCheck,
): value is CloudPack[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  const byMonth = new Map(shards.map((shard) => [shard.month, shard]));
  const flattened: string[] = [];
  const paths: string[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return false;
    const pack = item as Partial<CloudPack>;
    if (
      !Array.isArray(pack.months) ||
      pack.months.length < 1 ||
      pack.months.length > PACK_MONTHS ||
      !pack.months.every((month) => typeof month === "string") ||
      !isCounts(pack.counts) ||
      typeof pack.count !== "number" ||
      !Number.isSafeInteger(pack.count) ||
      pack.count < 0 ||
      !isAsset(pack.points) ||
      !PATH.test(pack.points.path)
    ) {
      return false;
    }
    const members = pack.months.map((month) => byMonth.get(month));
    if (members.some((shard) => !shard)) return false;
    const group = members as PackShard[];
    const key = packKey(pack.months[0]);
    if (
      key == null ||
      pack.points.path !== packPath(key) ||
      !pack.months.every((month) => packKey(month) === key) ||
      pack.count !== group.reduce((sum, shard) => sum + shard.count, 0) ||
      !sameCounts(pack.counts, sumCounts(group)) ||
      pack.points.bytes !== 12 + pack.count * 13
    ) {
      return false;
    }
    flattened.push(...pack.months);
    paths.push(pack.points.path);
  }
  const months = shards.map((shard) => shard.month);
  return (
    flattened.join() === months.join() &&
    paths.join() === [...new Set(paths)].sort().join()
  );
}

export function pointUnits<Shard extends PackShard>(
  shards: Shard[],
  packs?: CloudPack[],
): PointUnit<Shard>[] {
  if (!packs) {
    return shards.map((shard) => ({
      count: shard.count,
      counts: shard.counts,
      magic: "ATLASPT1",
      points: (shard as Shard & { points: PackAsset }).points,
      shards: [shard],
    }));
  }
  const byMonth = new Map(shards.map((shard) => [shard.month, shard]));
  return packs.map((pack) => ({
    count: pack.count,
    counts: pack.counts,
    magic: "ATLASPK1",
    points: pack.points,
    shards: pack.months.map((month) => byMonth.get(month)!),
  }));
}

export async function loadPoint<Shard extends PackShard>(
  unit: PointUnit<Shard>,
  signal: AbortSignal,
  fetcher: typeof fetch,
  url: string,
  digest: Digest,
): Promise<PointData> {
  const label = unit.magic === "ATLASPK1" ? "pack" : "shard";
  const response = await fetcher(url, { signal, cache: "force-cache" });
  if (!response.ok) throw new Error(`Paper point request failed (${response.status})`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== unit.points.bytes) {
    throw new Error(`Paper point byte length does not match its index`);
  }
  if ((await digest(bytes)) !== unit.points.sha256) {
    throw new Error(`Paper point digest does not match its index`);
  }
  const view = new DataView(bytes);
  const magic = new TextDecoder().decode(new Uint8Array(bytes, 0, 8));
  const count = view.getUint32(8, true);
  if (
    magic !== unit.magic ||
    count !== unit.count ||
    bytes.byteLength !== 12 + count * 13
  ) {
    throw new Error(`Paper point ${label} has an invalid contract`);
  }
  const source = LITTLE_ENDIAN ? new Float32Array(bytes, 12, count * 3) : null;
  let radius = 0;
  for (let index = 0; index < count; index += 1) {
    const offset = index * 3;
    const x = source?.[offset] ?? view.getFloat32(12 + offset * 4, true);
    const y = source?.[offset + 1] ?? view.getFloat32(16 + offset * 4, true);
    const z = source?.[offset + 2] ?? view.getFloat32(20 + offset * 4, true);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
      throw new Error(`Paper point ${label} is invalid`);
    }
    radius = Math.max(radius, Math.hypot(x, y, z));
  }
  const scopes = new Uint8Array(bytes, 12 + count * 12, count);
  const counts = [0, 0, 0];
  for (const scope of scopes) {
    if (scope > 2) throw new Error(`Paper point ${label} is invalid`);
    counts[scope] += 1;
  }
  if (
    counts[0] !== unit.counts.likely ||
    counts[1] !== unit.counts.possible ||
    counts[2] !== unit.counts.outside
  ) {
    throw new Error(`Paper point ${label} is invalid`);
  }
  return { count, positions: source, radius, scopes, view };
}
