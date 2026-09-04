import { hasOnlyKeys, isRecord, isString } from "./guards";
import {
  methodCount,
  methodOrder,
  readMethodRow,
  readMethodRows,
  type MethodIdentity,
  type MethodIndex,
  type MethodRow,
  type MethodSummary,
} from "./methods";

const DIGEST = /^[0-9a-f]{64}$/;
const ROW_KEYS = [
  "id",
  "status",
  "label",
  "kind",
  "head",
  "support_count",
  "mention_count",
  "first_year",
  "last_year",
  "scope_counts",
];

function readIdentity(value: unknown, minimum: number): MethodIdentity | null {
  const keys = new Set([...ROW_KEYS, "ordinal", "full_row_sha256"]);
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, keys) ||
    Object.keys(value).length !== keys.size ||
    !methodCount(value.ordinal) ||
    !isString(value.full_row_sha256) ||
    !DIGEST.test(value.full_row_sha256)
  ) {
    return null;
  }
  const compact = Object.fromEntries(ROW_KEYS.map((key) => [key, value[key]]));
  const row = readMethodRow(compact, minimum);
  return row
    ? { ...row, ordinal: value.ordinal, fullRowDigest: value.full_row_sha256 }
    : null;
}

function readIdentities(
  values: unknown,
  minimum: number,
  expected: number,
): MethodIdentity[] | null {
  if (!Array.isArray(values) || values.length !== expected) return null;
  const rows = values.map((value) => readIdentity(value, minimum));
  if (rows.some((row) => row === null)) return null;
  const valid = rows as MethodIdentity[];
  if (
    new Set(valid.map((row) => row.id)).size !== valid.length ||
    new Set(valid.map((row) => row.label)).size !== valid.length ||
    valid.some(
      (row, position) =>
        row.ordinal !== position ||
        (position > 0 && methodOrder(valid[position - 1], row) > 0),
    )
  ) {
    return null;
  }
  return valid;
}

export function readMethodTop(value: unknown, index: MethodIndex): MethodRow[] | null {
  const keys = new Set([
    "schema_version",
    "corpus_manifest_sha256",
    ...(index.tier === "catalog-only" ? ["full_asset_sha256"] : []),
    "order",
    "rows",
  ]);
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, keys) ||
    Object.keys(value).length !== keys.size ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    (index.tier === "catalog-only" &&
      value.full_asset_sha256 !== index.download.sha256) ||
    value.order !== "support-desc-label-asc-head-asc"
  ) {
    return null;
  }
  const expected = Math.min(200, index.qualifiedCandidates);
  return index.tier === "catalog-only"
    ? readIdentities(value.rows, index.minimumSupport, expected)
    : readMethodRows(value.rows, index.minimumSupport, expected);
}

export function isMethodIdentity(row: MethodRow): row is MethodIdentity {
  return "ordinal" in row && "fullRowDigest" in row;
}

export function methodSummaryText(summary: MethodSummary): string {
  return `${summary.sourceCount.toLocaleString()} abstracts scanned · ${summary.distinctCandidates.toLocaleString()} distinct phrases · ${summary.qualifiedCandidates.toLocaleString()} appearing in at least ${summary.minimumSupport.toLocaleString()} papers.`;
}

export function normalizeMethodQuery(value: string): string {
  return value
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}
