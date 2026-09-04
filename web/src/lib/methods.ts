import { hasOnlyKeys, isNumber, isRecord, isString, type RecordValue } from "./guards";

export const METHOD_CANDIDATE_NOTICE =
  "Lexical phrases extracted from abstracts; not reviewed techniques, novelty claims, evidence of effectiveness, or recommendations.";
export const METHOD_RELEASE_NOTICE =
  "Evidence spans are available only in the immutable full release download.";
export const METHOD_QUERY_DELAY_MS = 275;

export const METHOD_CAPS = {
  index: 8_192,
  summary: 32_768,
  top: 131_072,
  router: 65_536,
  search: 262_144,
  detail: 131_072,
} as const;

const DIGEST = /^[0-9a-f]{64}$/;
const ID = /^method-candidate:[0-9a-f]{64}$/;
const YEAR = /^[0-9]{4}$/;
const SUMMARY_PATH = /^summary-[0-9a-f]{16}\.json$/;
const TOP_PATH = /^top-[0-9a-f]{16}\.json$/;
const SEARCH_PATH = /^search-[0-9a-f]{16}\.json$/;
const DETAILS_PATH = /^details-[0-9a-f]{16}\.json$/;
const RELEASE_URL =
  /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/releases\/download\/[A-Za-z0-9][A-Za-z0-9._-]{0,99}\/candidates(?:-[0-9a-f]{64})?\.jsonl\.gz$/;
const LOCAL_KEYS = new Set(["path", "encoding", "sha256", "bytes", "row_count"]);
const ROW_KEYS = new Set([
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
]);
const SCOPE_KEYS = new Set(["likely", "possible", "outside"]);

export type MethodScopeCounts = { likely: number; possible: number; outside: number };

export type MethodRow = {
  id: string;
  label: string;
  kind: "method-noun" | "process-technique";
  head: string;
  supportCount: number;
  mentionCount: number;
  firstYear: string;
  lastYear: string;
  scopeCounts: MethodScopeCounts;
};

export type MethodIdentity = MethodRow & {
  ordinal: number;
  fullRowDigest: string;
};

export type MethodEvidence = {
  sourceId: string;
  field: "abstract";
  span: [number, number];
  text: string;
  published: string;
  primaryCategory: string;
};

export type MethodCandidate = MethodRow & { evidence: MethodEvidence[] };

export type MethodAsset = {
  path: string;
  encoding: "json";
  sha256: string;
  bytes: number;
  rowCount: number;
};

export type MethodDownload = {
  url: string;
  encoding: "jsonl+gzip";
  sha256: string;
  bytes: number;
  rowCount: number;
};

export type MethodFamily = {
  id: string;
  label: string;
  paperCount: number;
};

export type MethodIndex = {
  tier: "full-evidence" | "catalog-only";
  corpusDigest: string;
  sourceCount: number;
  monthCount: number;
  minimumSupport: number;
  maximumEvidence: number;
  scannedAbstracts: number;
  distinctCandidates: number;
  qualifiedCandidates: number;
  families: MethodFamily[];
  summary: MethodAsset;
  top: MethodAsset;
  search: MethodAsset;
  details: MethodAsset;
  download: MethodDownload;
  notice: string;
};

export type MethodSummary = {
  corpusDigest: string;
  sourceCount: number;
  minimumSupport: number;
  qualifiedCandidates: number;
  distinctCandidates: number;
  families: MethodFamily[];
  byKind: { kind: MethodRow["kind"]; count: number }[];
  byScope: { scope: keyof MethodScopeCounts; count: number }[];
  bySupport: { minimum: number; maximum: number | null; count: number }[];
  byFirstYear: { year: string; count: number }[];
};

export type MethodOverview = {
  index: MethodIndex;
  summary: MethodSummary;
  top: MethodRow[];
};

function exact(value: RecordValue, keys: ReadonlySet<string>): boolean {
  return hasOnlyKeys(value, keys) && Object.keys(value).length === keys.size;
}

export function methodCount(value: unknown): value is number {
  return isNumber(value) && Number.isSafeInteger(value) && value >= 0;
}

function filled(value: unknown, limit: number): value is string {
  return isString(value) && value.length > 0 && value.length <= limit;
}

function family(value: unknown, sourceCount: number): MethodFamily | null {
  const keys = new Set(["id", "status", "label", "paper_count"]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    !filled(value.id, 100) ||
    value.status !== "curated-family" ||
    !filled(value.label, 100) ||
    !methodCount(value.paper_count) ||
    value.paper_count > sourceCount
  ) {
    return null;
  }
  return { id: value.id, label: value.label, paperCount: value.paper_count };
}

function addressed(path: string, sha256: string): boolean {
  return path.endsWith(`-${sha256.slice(0, 16)}.json`);
}

function localAsset(value: unknown, pattern: RegExp, cap: number): MethodAsset | null {
  if (
    !isRecord(value) ||
    !exact(value, LOCAL_KEYS) ||
    !isString(value.path) ||
    !pattern.test(value.path) ||
    value.encoding !== "json" ||
    !isString(value.sha256) ||
    !DIGEST.test(value.sha256) ||
    !addressed(value.path, value.sha256) ||
    !methodCount(value.bytes) ||
    value.bytes < 2 ||
    value.bytes > cap ||
    !methodCount(value.row_count)
  ) {
    return null;
  }
  return {
    path: value.path,
    encoding: "json",
    sha256: value.sha256,
    bytes: value.bytes,
    rowCount: value.row_count,
  };
}

function download(value: unknown, rows: number): MethodDownload | null {
  const keys = new Set(["url", "encoding", "sha256", "bytes", "row_count"]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    !isString(value.url) ||
    !RELEASE_URL.test(value.url) ||
    value.encoding !== "jsonl+gzip" ||
    !isString(value.sha256) ||
    !DIGEST.test(value.sha256) ||
    !methodCount(value.bytes) ||
    value.bytes < 1 ||
    value.row_count !== rows
  ) {
    return null;
  }
  try {
    new URL(value.url);
  } catch {
    return null;
  }
  return {
    url: value.url,
    encoding: "jsonl+gzip",
    sha256: value.sha256,
    bytes: value.bytes,
    rowCount: rows,
  };
}

export function readMethodRow(value: unknown, minimum: number): MethodRow | null {
  if (
    !isRecord(value) ||
    !exact(value, ROW_KEYS) ||
    !isString(value.id) ||
    !ID.test(value.id) ||
    value.status !== "corpus-extracted-candidate" ||
    !filled(value.label, 160) ||
    (value.kind !== "method-noun" && value.kind !== "process-technique") ||
    !filled(value.head, 32) ||
    !methodCount(value.support_count) ||
    value.support_count < minimum ||
    !methodCount(value.mention_count) ||
    value.mention_count < value.support_count ||
    !isString(value.first_year) ||
    !YEAR.test(value.first_year) ||
    !isString(value.last_year) ||
    !YEAR.test(value.last_year) ||
    value.first_year > value.last_year ||
    !isRecord(value.scope_counts) ||
    !exact(value.scope_counts, SCOPE_KEYS)
  ) {
    return null;
  }
  const { likely, possible, outside } = value.scope_counts;
  if (
    !methodCount(likely) ||
    !methodCount(possible) ||
    !methodCount(outside) ||
    likely + possible + outside !== value.support_count
  ) {
    return null;
  }
  return {
    id: value.id,
    label: value.label,
    kind: value.kind,
    head: value.head,
    supportCount: value.support_count,
    mentionCount: value.mention_count,
    firstYear: value.first_year,
    lastYear: value.last_year,
    scopeCounts: { likely, possible, outside },
  };
}

export function methodOrder(left: MethodRow, right: MethodRow): number {
  const compare = (first: string, second: string) =>
    first < second ? -1 : first > second ? 1 : 0;
  return (
    right.supportCount - left.supportCount ||
    compare(left.label, right.label) ||
    compare(left.head, right.head) ||
    compare(left.id, right.id)
  );
}

export function readMethodRows(
  values: unknown,
  minimum: number,
  expected: number,
): MethodRow[] | null {
  if (!Array.isArray(values) || values.length !== expected) return null;
  const rows = values.map((value) => readMethodRow(value, minimum));
  if (rows.some((row) => row === null)) return null;
  const valid = rows as MethodRow[];
  if (
    new Set(valid.map((row) => row.id)).size !== valid.length ||
    new Set(valid.map((row) => row.label)).size !== valid.length ||
    valid.some((row, index) => index > 0 && methodOrder(valid[index - 1], row) > 0)
  ) {
    return null;
  }
  return valid;
}

const INDEX_KEYS = new Set([
  "schema_version",
  "generator_version",
  "status",
  "tier",
  "corpus",
  "extraction",
  "coverage",
  "curated_families",
  "assets",
  "notice",
]);

export function readMethodIndex(value: unknown): MethodIndex | null {
  const corpusKeys = new Set(["manifest_sha256", "source_count", "month_count"]);
  const extractionKeys = new Set([
    "normalization_version",
    "minimum_support",
    "maximum_evidence",
    "candidate_limit",
  ]);
  const coverageKeys = new Set([
    "scanned_papers",
    "scanned_abstracts",
    "quarantined_abstracts",
    "extracted_mentions",
    "distinct_extracted_candidates",
    "qualified_candidates",
  ]);
  const assetKeys = new Set(["summary", "top", "search", "details", "download"]);
  if (
    !isRecord(value) ||
    !exact(value, INDEX_KEYS) ||
    value.schema_version !== 1 ||
    value.generator_version !== "methods-browser-1" ||
    value.status !== "corpus-extracted-candidates" ||
    (value.tier !== "full-evidence" && value.tier !== "catalog-only") ||
    !isRecord(value.corpus) ||
    !exact(value.corpus, corpusKeys) ||
    !isRecord(value.extraction) ||
    !exact(value.extraction, extractionKeys) ||
    !isRecord(value.coverage) ||
    !exact(value.coverage, coverageKeys) ||
    !Array.isArray(value.curated_families) ||
    !isRecord(value.assets) ||
    !exact(value.assets, assetKeys) ||
    !filled(value.notice, 1_000)
  ) {
    return null;
  }
  const digest = value.corpus.manifest_sha256;
  const source = value.corpus.source_count;
  const months = value.corpus.month_count;
  const minimum = value.extraction.minimum_support;
  const distinct = value.coverage.distinct_extracted_candidates;
  const qualified = value.coverage.qualified_candidates;
  if (
    !isString(digest) ||
    !DIGEST.test(digest) ||
    !methodCount(source) ||
    source < 1 ||
    !methodCount(months) ||
    months < 1 ||
    value.extraction.normalization_version !== "method-phrase-1" ||
    !methodCount(minimum) ||
    minimum < 1 ||
    value.extraction.maximum_evidence !== 6 ||
    value.extraction.candidate_limit !== null ||
    value.coverage.scanned_papers !== source ||
    value.coverage.scanned_abstracts !== source ||
    !methodCount(value.coverage.quarantined_abstracts) ||
    value.coverage.quarantined_abstracts > source ||
    !methodCount(value.coverage.extracted_mentions) ||
    !methodCount(distinct) ||
    !methodCount(qualified) ||
    qualified > distinct ||
    distinct > value.coverage.extracted_mentions ||
    value.coverage.extracted_mentions < qualified * minimum
  ) {
    return null;
  }
  const families = value.curated_families.map((item) => family(item, source));
  const summary = localAsset(value.assets.summary, SUMMARY_PATH, METHOD_CAPS.summary);
  const top = localAsset(value.assets.top, TOP_PATH, METHOD_CAPS.top);
  const search = localAsset(value.assets.search, SEARCH_PATH, METHOD_CAPS.router);
  const details = localAsset(value.assets.details, DETAILS_PATH, METHOD_CAPS.router);
  const full = download(value.assets.download, qualified);
  if (
    families.length !== 24 ||
    families.some((item) => item === null) ||
    new Set(families.map((item) => item?.id)).size !== 24 ||
    families.map((item) => item?.id ?? "").join() !==
      [...families.map((item) => item?.id ?? "")].sort().join() ||
    !summary ||
    !top ||
    !search ||
    !details ||
    !full ||
    (value.tier === "catalog-only" && !value.notice.includes(METHOD_RELEASE_NOTICE)) ||
    summary.rowCount !== 1 ||
    top.rowCount !== Math.min(200, qualified) ||
    details.rowCount !== qualified ||
    search.rowCount < qualified
  ) {
    return null;
  }
  return {
    tier: value.tier,
    corpusDigest: digest,
    sourceCount: source,
    monthCount: months,
    minimumSupport: minimum,
    maximumEvidence: 6,
    scannedAbstracts: source,
    distinctCandidates: distinct,
    qualifiedCandidates: qualified,
    families: families as MethodFamily[],
    summary,
    top,
    search,
    details,
    download: full,
    notice: value.notice,
  };
}

export function readMethodSummary(
  value: unknown,
  index: MethodIndex,
): MethodSummary | null {
  const keys = new Set([
    "schema_version",
    "corpus_manifest_sha256",
    "qualified_candidates",
    "distinct_extracted_candidates",
    "curated_families",
    "by_kind",
    "by_scope",
    "by_support",
    "by_first_year",
  ]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    value.qualified_candidates !== index.qualifiedCandidates ||
    value.distinct_extracted_candidates !== index.distinctCandidates ||
    !Array.isArray(value.curated_families) ||
    !Array.isArray(value.by_kind) ||
    !Array.isArray(value.by_scope) ||
    !Array.isArray(value.by_support) ||
    !Array.isArray(value.by_first_year)
  ) {
    return null;
  }
  const families = value.curated_families.map((item) =>
    family(item, index.sourceCount),
  );
  const kinds = ["method-noun", "process-technique"] as const;
  const scopes = ["likely", "possible", "outside"] as const;
  const byKind = value.by_kind.map((item, position) => {
    if (
      !isRecord(item) ||
      !exact(item, new Set(["kind", "count"])) ||
      item.kind !== kinds[position] ||
      !methodCount(item.count)
    )
      return null;
    return { kind: item.kind, count: item.count };
  });
  const byScope = value.by_scope.map((item, position) => {
    if (
      !isRecord(item) ||
      !exact(item, new Set(["scope", "count"])) ||
      item.scope !== scopes[position] ||
      !methodCount(item.count)
    )
      return null;
    return { scope: item.scope, count: item.count };
  });
  const thresholds = [
    index.minimumSupport,
    ...[10, 100, 1_000, 10_000].filter((item) => item > index.minimumSupport),
  ];
  const bySupport = value.by_support.map((item, position) => {
    const next = thresholds[position + 1];
    if (
      !isRecord(item) ||
      !exact(item, new Set(["minimum", "maximum", "count"])) ||
      item.minimum !== thresholds[position] ||
      item.maximum !== (next === undefined ? null : next - 1) ||
      !methodCount(item.count)
    )
      return null;
    return { minimum: item.minimum, maximum: item.maximum, count: item.count };
  });
  const byFirstYear = value.by_first_year.map((item) => {
    if (
      !isRecord(item) ||
      !exact(item, new Set(["year", "count"])) ||
      !isString(item.year) ||
      !YEAR.test(item.year) ||
      !methodCount(item.count)
    )
      return null;
    return { year: item.year, count: item.count };
  });
  const familyRows = families as MethodFamily[];
  if (
    families.length !== 24 ||
    families.some((item) => item === null) ||
    JSON.stringify(familyRows) !== JSON.stringify(index.families) ||
    byKind.length !== 2 ||
    byKind.some((item) => item === null) ||
    byKind.reduce((sum, item) => sum + (item?.count ?? 0), 0) !==
      index.qualifiedCandidates ||
    byScope.length !== 3 ||
    byScope.some((item) => item === null) ||
    byScope.reduce((sum, item) => sum + (item?.count ?? 0), 0) <
      index.qualifiedCandidates * index.minimumSupport ||
    bySupport.length !== thresholds.length ||
    bySupport.some((item) => item === null) ||
    bySupport.reduce((sum, item) => sum + (item?.count ?? 0), 0) !==
      index.qualifiedCandidates ||
    byFirstYear.some((item) => item === null) ||
    byFirstYear.reduce((sum, item) => sum + (item?.count ?? 0), 0) !==
      index.qualifiedCandidates
  ) {
    return null;
  }
  const years = byFirstYear.map((item) => item?.year ?? "");
  if (years.join() !== [...new Set(years)].sort().join()) return null;
  return {
    corpusDigest: index.corpusDigest,
    sourceCount: index.sourceCount,
    minimumSupport: index.minimumSupport,
    qualifiedCandidates: index.qualifiedCandidates,
    distinctCandidates: index.distinctCandidates,
    families: familyRows,
    byKind: byKind as MethodSummary["byKind"],
    byScope: byScope as MethodSummary["byScope"],
    bySupport: bySupport as MethodSummary["bySupport"],
    byFirstYear: byFirstYear as MethodSummary["byFirstYear"],
  };
}
