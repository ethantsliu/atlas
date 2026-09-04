import { hasOnlyKeys, isRecord, isString, type RecordValue } from "./guards";
import {
  methodCount,
  methodOrder,
  readMethodRow,
  type MethodCandidate,
  type MethodEvidence,
  type MethodIdentity,
  type MethodIndex,
} from "./methods";

function exact(value: RecordValue, keys: ReadonlySet<string>): boolean {
  return hasOnlyKeys(value, keys) && Object.keys(value).length === keys.size;
}

const IDENTITY_COLUMNS = [
  "ordinal",
  "full_row_sha256",
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
] as const;

export function readIdentityRows(
  value: unknown,
  index: MethodIndex,
  prefix: string,
  start: number,
  end: number,
  expected: number,
): MethodIdentity[] | null {
  const keys = new Set([
    "schema_version",
    "corpus_manifest_sha256",
    "full_asset_sha256",
    "route_kind",
    "route_mode",
    "prefix",
    "start_ordinal",
    "end_ordinal",
    "columns",
    "rows",
  ]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    value.full_asset_sha256 !== index.download.sha256 ||
    value.route_kind !== "detail" ||
    value.route_mode !== "ordinal" ||
    value.prefix !== prefix ||
    value.start_ordinal !== start ||
    value.end_ordinal !== end ||
    !Array.isArray(value.columns) ||
    value.columns.length !== IDENTITY_COLUMNS.length ||
    value.columns.some((column, position) => column !== IDENTITY_COLUMNS[position]) ||
    !Array.isArray(value.rows) ||
    value.rows.length !== expected ||
    end - start + 1 !== expected
  ) {
    return null;
  }
  const rows = value.rows.map((item) =>
    Array.isArray(item) && item.length === IDENTITY_COLUMNS.length
      ? readIdentity(
          Object.fromEntries(
            IDENTITY_COLUMNS.map((column, position) => [column, item[position]]),
          ),
          index.minimumSupport,
        )
      : null,
  );
  if (rows.some((row) => row === null)) return null;
  const valid = rows as MethodIdentity[];
  if (
    new Set(valid.map((row) => row.id)).size !== valid.length ||
    new Set(valid.map((row) => row.label)).size !== valid.length ||
    valid.some(
      (row, position) =>
        row.ordinal !== start + position ||
        (position > 0 && methodOrder(valid[position - 1], row) > 0),
    )
  ) {
    return null;
  }
  return valid;
}

function readIdentity(value: unknown, minimum: number): MethodIdentity | null {
  if (!isRecord(value)) return null;
  const extras = new Set(["ordinal", "full_row_sha256"]);
  const compactKeys = [
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
  const keys = new Set([...compactKeys, ...extras]);
  if (
    !exact(value, keys) ||
    !methodCount(value.ordinal) ||
    !isString(value.full_row_sha256) ||
    !/^[0-9a-f]{64}$/.test(value.full_row_sha256)
  ) {
    return null;
  }
  const compact = Object.fromEntries(compactKeys.map((key) => [key, value[key]]));
  const row = readMethodRow(compact, minimum);
  return row
    ? { ...row, ordinal: value.ordinal, fullRowDigest: value.full_row_sha256 }
    : null;
}

function readEvidence(value: unknown): MethodEvidence | null {
  const keys = new Set([
    "source_id",
    "field",
    "span",
    "text",
    "published",
    "primary_category",
  ]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    !isString(value.source_id) ||
    !/^arxiv:(?:[0-9]{4}\.[0-9]{4,5}|[a-z]+(?:[.-][a-z]+)*\/[0-9]{7})$/.test(
      value.source_id,
    ) ||
    value.field !== "abstract" ||
    !Array.isArray(value.span) ||
    value.span.length !== 2 ||
    !methodCount(value.span[0]) ||
    !methodCount(value.span[1]) ||
    value.span[1] <= value.span[0] ||
    !isString(value.text) ||
    value.text.length < 1 ||
    value.text.length > 160 ||
    !isString(value.published) ||
    value.published.length < 10 ||
    value.published.length > 64 ||
    !isString(value.primary_category) ||
    value.primary_category.length < 1 ||
    value.primary_category.length > 64
  ) {
    return null;
  }
  return {
    sourceId: value.source_id,
    field: "abstract",
    span: [value.span[0], value.span[1]],
    text: value.text,
    published: value.published,
    primaryCategory: value.primary_category,
  };
}

export function readMethodCandidate(
  value: unknown,
  index: MethodIndex,
): MethodCandidate | null {
  const keys = new Set([
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
    "evidence",
  ]);
  if (!isRecord(value) || !exact(value, keys) || !Array.isArray(value.evidence)) {
    return null;
  }
  const compact = Object.fromEntries(
    [...keys].filter((key) => key !== "evidence").map((key) => [key, value[key]]),
  );
  const row = readMethodRow(compact, index.minimumSupport);
  const sources = value.evidence.map(readEvidence);
  if (
    !row ||
    sources.length < 1 ||
    sources.length > index.maximumEvidence ||
    sources.some((item) => item === null)
  ) {
    return null;
  }
  const valid = sources as MethodEvidence[];
  const order = valid.map(
    (item) =>
      `${item.sourceId}\0${item.span[0].toString().padStart(12, "0")}\0${item.span[1].toString().padStart(12, "0")}\0${item.text}`,
  );
  if (order.join() !== [...new Set(order)].sort().join()) return null;
  return { ...row, evidence: valid };
}

export function readMethodDetails(
  value: unknown,
  index: MethodIndex,
  prefix: string,
  expected: number,
): MethodCandidate[] | null {
  const keys = new Set(["schema_version", "corpus_manifest_sha256", "prefix", "rows"]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    value.prefix !== prefix ||
    !Array.isArray(value.rows) ||
    value.rows.length !== expected
  ) {
    return null;
  }
  const rows = value.rows.map((row) => readMethodCandidate(row, index));
  if (rows.some((row) => row === null)) return null;
  const valid = rows as MethodCandidate[];
  if (
    new Set(valid.map((row) => row.id)).size !== valid.length ||
    valid.some(
      (row, position) =>
        !row.id.slice("method-candidate:".length).startsWith(prefix) ||
        (position > 0 && methodOrder(valid[position - 1], row) > 0),
    )
  ) {
    return null;
  }
  return valid;
}
