import { hasOnlyKeys, isRecord, isString, type RecordValue } from "./guards";
import {
  METHOD_CAPS,
  methodCount,
  readMethodRows,
  type MethodAsset,
  type MethodIndex,
  type MethodRow,
} from "./methods";
import { normalizeMethodQuery } from "./methodview";

const DIGEST = /^[0-9a-f]{64}$/;
const SEARCH_LEAF = /^search-[0-9a-z]{3,12}-[0-9a-f]{16}\.json$/;
const DETAIL_LEAF = /^detail-[0-9a-f]{2,8}-[0-9a-f]{16}\.json$/;
const SEARCH_ROUTE = /^search-route-[0-9a-f]{16}\.json$/;
const DETAIL_ROUTE = /^detail-route-[0-9a-f]{16}\.json$/;
const NODE_BASE = ["path", "encoding", "sha256", "bytes", "row_count"];

export type MethodRoute = "search" | "detail";
export type RouteMode = "word" | "hash" | "ordinal";
export type MethodNode = MethodAsset & {
  kind: "leaf" | "router";
  prefix: string;
  routeMode?: RouteMode;
  hashPrefix?: string;
  startOrdinal?: number;
  endOrdinal?: number;
};
export type MethodRoot = { rowCount: number; shards: MethodNode[] };
export type SearchLeaf = { rows?: MethodRow[]; ordinals?: number[] };

function exact(value: RecordValue, keys: ReadonlySet<string>): boolean {
  return hasOnlyKeys(value, keys) && Object.keys(value).length === keys.size;
}

function addressed(path: string, digest: string): boolean {
  return path.endsWith(`-${digest.slice(0, 16)}.json`);
}

function nodeKeys(value: RecordValue): Set<string> {
  return new Set([
    ...NODE_BASE,
    "kind",
    "prefix",
    ...(value.route_mode === undefined ? [] : ["route_mode"]),
    ...(value.hash_prefix === undefined ? [] : ["hash_prefix"]),
    ...(value.start_ordinal === undefined ? [] : ["start_ordinal"]),
    ...(value.end_ordinal === undefined ? [] : ["end_ordinal"]),
  ]);
}

export function readMethodNode(
  value: unknown,
  route: MethodRoute,
  tier: MethodIndex["tier"],
): MethodNode | null {
  if (!isRecord(value) || (value.kind !== "leaf" && value.kind !== "router")) {
    return null;
  }
  const mode = value.route_mode;
  const hash = value.hash_prefix;
  const ordinal = route === "detail" && tier === "catalog-only";
  if (
    !exact(value, nodeKeys(value)) ||
    !isString(value.path) ||
    value.encoding !== "json" ||
    !isString(value.sha256) ||
    !DIGEST.test(value.sha256) ||
    !addressed(value.path, value.sha256) ||
    !methodCount(value.bytes) ||
    value.bytes < 2 ||
    !methodCount(value.row_count) ||
    value.row_count < 1 ||
    !isString(value.prefix)
  ) {
    return null;
  }
  if (ordinal) {
    if (
      mode !== "ordinal" ||
      !/^[0-9a-f]{8}$/.test(value.prefix) ||
      !methodCount(value.start_ordinal) ||
      !methodCount(value.end_ordinal) ||
      value.end_ordinal < value.start_ordinal ||
      value.end_ordinal - value.start_ordinal + 1 !== value.row_count ||
      hash !== undefined
    ) {
      return null;
    }
  } else {
    if (value.start_ordinal !== undefined || value.end_ordinal !== undefined)
      return null;
    if (value.kind === "router" && mode !== "word" && mode !== "hash") return null;
    if (value.kind === "leaf" && mode !== undefined && mode !== "hash") return null;
    if (route === "detail" && (mode === "word" || hash !== undefined)) return null;
  }
  if (route === "search") {
    if (!/^[a-z0-9]{0,12}$/.test(value.prefix)) return null;
    if (hash !== undefined && (!isString(hash) || !/^[0-9a-f]{0,8}$/.test(hash))) {
      return null;
    }
    if (value.kind === "router" && mode === "hash" && hash === undefined) return null;
    if (mode === "word" && hash !== undefined) return null;
    if (value.kind === "leaf" && value.prefix.length < 3) return null;
  } else if (!ordinal && !/^[0-9a-f]{0,8}$/.test(value.prefix)) {
    return null;
  }
  const pattern =
    value.kind === "router"
      ? route === "search"
        ? SEARCH_ROUTE
        : DETAIL_ROUTE
      : route === "search"
        ? SEARCH_LEAF
        : DETAIL_LEAF;
  const cap =
    value.kind === "router"
      ? METHOD_CAPS.router
      : route === "search"
        ? METHOD_CAPS.search
        : METHOD_CAPS.detail;
  if (!pattern.test(value.path) || value.bytes > cap) return null;
  return {
    path: value.path,
    encoding: "json",
    sha256: value.sha256,
    bytes: value.bytes,
    rowCount: value.row_count,
    kind: value.kind,
    prefix: value.prefix,
    routeMode: mode as RouteMode | undefined,
    hashPrefix: hash as string | undefined,
    startOrdinal: value.start_ordinal as number | undefined,
    endOrdinal: value.end_ordinal as number | undefined,
  };
}

export function readMethodNodes(
  values: unknown,
  route: MethodRoute,
  index: MethodIndex,
): MethodNode[] | null {
  if (!Array.isArray(values) || values.length < 1) return null;
  const nodes = values.map((value) => readMethodNode(value, route, index.tier));
  if (nodes.some((node) => node === null)) return null;
  const valid = nodes as MethodNode[];
  if (new Set(valid.map((node) => node.path)).size !== valid.length) return null;
  const keys = valid.map((node) =>
    [node.prefix, node.hashPrefix ?? "", node.startOrdinal ?? -1, node.path].join("\0"),
  );
  return keys.join() === [...keys].sort().join() ? valid : null;
}

export function nodeRows(nodes: readonly MethodNode[]): number {
  return nodes.reduce((total, node) => total + node.rowCount, 0);
}

export function readSearchRoot(value: unknown, index: MethodIndex): MethodRoot | null {
  const catalog = index.tier === "catalog-only";
  const keys = new Set([
    "schema_version",
    "corpus_manifest_sha256",
    ...(catalog ? ["full_asset_sha256"] : []),
    "normalization",
    "minimum_query_length",
    "row_count",
    "shards",
  ]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    (catalog && value.full_asset_sha256 !== index.download.sha256) ||
    value.normalization !== "nfkc-lower-alnum-space-1" ||
    value.minimum_query_length !== 3 ||
    value.row_count !== index.search.rowCount
  ) {
    return null;
  }
  const shards = readMethodNodes(value.shards, "search", index);
  return shards && nodeRows(shards) === value.row_count
    ? { rowCount: value.row_count, shards }
    : null;
}

export function readDetailRoot(value: unknown, index: MethodIndex): MethodRoot | null {
  const catalog = index.tier === "catalog-only";
  const keys = new Set(
    catalog
      ? [
          "schema_version",
          "corpus_manifest_sha256",
          "full_asset_sha256",
          "route_kind",
          "route_mode",
          "start_ordinal",
          "end_ordinal",
          "row_count",
          "shards",
        ]
      : [
          "schema_version",
          "corpus_manifest_sha256",
          "prefix_bits",
          "row_count",
          "shards",
        ],
  );
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    value.row_count !== index.details.rowCount
  ) {
    return null;
  }
  if (
    catalog
      ? value.full_asset_sha256 !== index.download.sha256 ||
        value.route_kind !== "detail" ||
        value.route_mode !== "ordinal" ||
        value.start_ordinal !== 0 ||
        value.end_ordinal !== index.qualifiedCandidates - 1
      : value.prefix_bits !== 8
  ) {
    return null;
  }
  const shards = readMethodNodes(value.shards, "detail", index);
  return shards && nodeRows(shards) === value.row_count
    ? { rowCount: value.row_count, shards }
    : null;
}

export function readRouter(
  value: unknown,
  index: MethodIndex,
  node: MethodNode,
  route: MethodRoute,
): MethodNode[] | null {
  const catalog = index.tier === "catalog-only";
  const ordinal = route === "detail" && catalog;
  const hash = route === "search" && node.routeMode === "hash";
  const keys = new Set([
    "schema_version",
    "corpus_manifest_sha256",
    ...(catalog ? ["full_asset_sha256"] : []),
    "route_kind",
    "route_mode",
    "prefix",
    ...(ordinal ? ["start_ordinal", "end_ordinal"] : []),
    "row_count",
    "shards",
    ...(hash ? ["hash_prefix"] : []),
  ]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    (catalog && value.full_asset_sha256 !== index.download.sha256) ||
    value.route_kind !== route ||
    value.route_mode !== node.routeMode ||
    value.prefix !== node.prefix ||
    value.row_count !== node.rowCount ||
    (hash && value.hash_prefix !== node.hashPrefix) ||
    (ordinal &&
      (value.start_ordinal !== node.startOrdinal ||
        value.end_ordinal !== node.endOrdinal))
  ) {
    return null;
  }
  const shards = readMethodNodes(value.shards, route, index);
  if (!shards || nodeRows(shards) !== node.rowCount) return null;
  const routes = shards.map((child) =>
    [child.prefix, child.hashPrefix ?? "", child.startOrdinal ?? -1].join("\0"),
  );
  if (new Set(routes).size !== routes.length) return null;
  if (ordinal) {
    let next = node.startOrdinal;
    for (const child of shards) {
      if (child.startOrdinal !== next) return null;
      next = (child.endOrdinal ?? -1) + 1;
    }
    if (next !== (node.endOrdinal ?? -1) + 1) return null;
  } else if (
    route === "detail" &&
    shards.some(
      (child) =>
        !child.prefix.startsWith(node.prefix) ||
        child.prefix.length <= node.prefix.length,
    )
  ) {
    return null;
  } else if (
    route === "search" &&
    node.routeMode === "word" &&
    shards.some((child) => {
      const terminal = child.routeMode === "hash" || child.hashPrefix !== undefined;
      return terminal
        ? child.prefix !== node.prefix
        : !child.prefix.startsWith(node.prefix) ||
            child.prefix.length <= node.prefix.length;
    })
  ) {
    return null;
  } else if (
    route === "search" &&
    node.routeMode === "hash" &&
    shards.some(
      (child) =>
        child.prefix !== node.prefix ||
        !child.hashPrefix?.startsWith(node.hashPrefix ?? "") ||
        child.hashPrefix.length <= (node.hashPrefix ?? "").length,
    )
  ) {
    return null;
  }
  return shards;
}

export function readSearchLeaf(
  value: unknown,
  index: MethodIndex,
  node: MethodNode,
): SearchLeaf | null {
  const catalog = index.tier === "catalog-only";
  const keys = new Set([
    "schema_version",
    "corpus_manifest_sha256",
    ...(catalog ? ["full_asset_sha256"] : []),
    "prefix",
    "hash_prefix",
    catalog ? "ordinals" : "rows",
  ]);
  if (
    !isRecord(value) ||
    !exact(value, keys) ||
    value.schema_version !== 1 ||
    value.corpus_manifest_sha256 !== index.corpusDigest ||
    (catalog && value.full_asset_sha256 !== index.download.sha256) ||
    value.prefix !== node.prefix ||
    value.hash_prefix !== (node.hashPrefix ?? "")
  ) {
    return null;
  }
  if (catalog) {
    if (!Array.isArray(value.ordinals) || value.ordinals.length !== node.rowCount) {
      return null;
    }
    const ordinals = value.ordinals;
    if (
      ordinals.some(
        (item, position) =>
          !methodCount(item) ||
          item >= index.qualifiedCandidates ||
          (position > 0 && ordinals[position - 1] >= item),
      )
    ) {
      return null;
    }
    return { ordinals: ordinals as number[] };
  }
  const rows = readMethodRows(value.rows, index.minimumSupport, node.rowCount);
  if (
    !rows ||
    rows.some(
      (row) =>
        normalizeMethodQuery(row.label)
          .split(" ")
          .every((word) => !word.startsWith(node.prefix)) ||
        (node.hashPrefix !== undefined &&
          !row.id.slice("method-candidate:".length).startsWith(node.hashPrefix)),
    )
  ) {
    return null;
  }
  return { rows };
}
