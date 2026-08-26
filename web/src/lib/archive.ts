import { isNumber, isRecord, isString, isStringArray } from "./guards";
import { basePath } from "./paths";

export type ArchiveCounts = {
  all: number;
  likely: number;
  possible: number;
  outside: number;
};

export type ArchiveShard = {
  month: string;
  path: string;
  sha256: string;
  bytes: number;
  days: number;
  dates: string[];
  counts: ArchiveCounts;
};

export type ArchiveManifest = {
  schema_version: 1;
  storage: "github-release";
  retention: string;
  counts: ArchiveCounts;
  shards: ArchiveShard[];
};

const MONTH = /^\d{4}-\d{2}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const SHARD = /^\d{4}-\d{2}\.json\.gz$/;
const DIGEST = /^[0-9a-f]{64}$/;
const SCOPES = ["all", "likely", "possible", "outside"] as const;

function isCount(value: unknown): value is number {
  return isNumber(value) && Number.isSafeInteger(value) && value >= 0;
}

function isCounts(value: unknown): value is ArchiveCounts {
  if (!isRecord(value)) return false;
  const { all, likely, possible, outside } = value;
  return (
    isCount(all) &&
    isCount(likely) &&
    isCount(possible) &&
    isCount(outside) &&
    all === likely + possible + outside
  );
}

function isShard(value: unknown): value is ArchiveShard {
  if (!isRecord(value)) return false;
  const { month, path, sha256, bytes, days, dates, counts } = value;
  return (
    isString(month) &&
    MONTH.test(month) &&
    isString(path) &&
    path === `${month}.json.gz` &&
    SHARD.test(path) &&
    isString(sha256) &&
    DIGEST.test(sha256) &&
    isCount(bytes) &&
    bytes > 0 &&
    isCount(days) &&
    isStringArray(dates) &&
    days === dates.length &&
    new Set(dates).size === dates.length &&
    dates.every((day) => DAY.test(day) && day.startsWith(month)) &&
    isCounts(counts)
  );
}

export function isArchiveManifest(value: unknown): value is ArchiveManifest {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    value.storage !== "github-release" ||
    !isString(value.retention) ||
    !isCounts(value.counts) ||
    !Array.isArray(value.shards) ||
    !value.shards.every(isShard)
  ) {
    return false;
  }
  const manifest = value as ArchiveManifest;
  const months = manifest.shards.map((shard) => shard.month);
  if (months.join() !== [...new Set(months)].sort().join()) return false;
  return SCOPES.every(
    (key) =>
      manifest.counts[key] ===
      manifest.shards.reduce((total, shard) => total + shard.counts[key], 0),
  );
}

export async function fetchArchive(
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<ArchiveManifest> {
  const response = await fetcher(basePath("/data/archive.json", base), {
    signal,
    cache: "no-cache",
  });
  if (!response.ok) throw new Error(`Archive request failed (${response.status})`);
  const value: unknown = await response.json();
  if (!isArchiveManifest(value)) throw new Error("Archive index has an invalid shape");
  return value;
}
