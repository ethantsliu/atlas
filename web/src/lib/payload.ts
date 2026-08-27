import type { Atlas, Idea, IdeaLayout, Paper } from "../types";
import { type RecordValue, hasOnlyKeys, isNumber, isRecord, isString } from "./guards";
import { isCoverage, isTaxon, isAtlasPayload } from "./atlas";
import { isCoreIdea, portfolioError } from "./idea";
import { atlasScope, layoutError, type LayoutScope } from "./semantic";

const CORE_KEYS = new Set([
  "schema_version",
  "meta",
  "coverage",
  "topics",
  "tricks",
  "repos",
  "ideas",
  "layout",
  "paper_asset",
]);
const META_KEYS = new Set([
  "generated_at",
  "paper_count",
  "research_entry_count",
  "context_entry_count",
  "repo_count",
  "idea_count",
  "full_reading_count",
  "extracted_fulltext_count",
  "notice",
]);
const ASSET_KEYS = new Set([
  "schema_version",
  "path",
  "sha256",
  "bytes",
  "paper_count",
]);
const BUNDLE_KEYS = new Set([
  "schema_version",
  "papers",
  "ideas",
  "idea_layout",
  "layout",
]);
const LEGACY_BUNDLE_KEYS = new Set(["schema_version", "papers", "layout"]);
const PAPER_PATH = /^\/data\/papers\/([0-9a-f]{64})\.json$/;
const LAYOUT_MAPS = ["positions", "neighbors", "node_clusters"] as const;
const LAYOUT_KEYS = new Set(LAYOUT_MAPS);

export type PaperAsset = {
  schema_version: 1;
  path: string;
  sha256: string;
  bytes: number;
  paper_count: number;
};

type Point3 = [number, number, number];
type Neighbor = { id: string; score: number };
type LayoutShard = {
  positions: Record<string, Point3>;
  neighbors: Record<string, Neighbor[]>;
  node_clusters: Record<string, string>;
};
type CoreLayout = Omit<
  NonNullable<Atlas["layout"]>,
  "positions" | "neighbors" | "node_clusters"
> &
  LayoutShard & { positions: Record<string, Point3> };

export type AtlasCore = Omit<Atlas, "papers" | "layout" | "idea_layout"> & {
  schema_version: 2;
  paper_asset: PaperAsset;
  layout: CoreLayout;
};

export type AtlasPreview = Omit<Atlas, "papers" | "layout"> & {
  papers: readonly [];
  layout: CoreLayout;
  complete: false;
};

export type AtlasRead = Atlas | AtlasPreview;

export type PaperBundle = {
  schema_version: 2;
  papers: Paper[];
  ideas: Idea[];
  idea_layout: IdeaLayout | null;
  layout: LayoutShard;
};

export type LegacyPaperBundle = {
  schema_version: 1;
  papers: Paper[];
  layout: LayoutShard;
};

type AcceptedPaperBundle = PaperBundle | LegacyPaperBundle;

function shardLayout(value: unknown): value is LayoutShard {
  if (!isRecord(value) || !hasOnlyKeys(value, LAYOUT_KEYS)) return false;
  if (!LAYOUT_MAPS.every((field) => isRecord(value[field]))) {
    return false;
  }
  const positions = isRecord(value.positions) ? Object.values(value.positions) : [];
  const neighbors = isRecord(value.neighbors) ? Object.values(value.neighbors) : [];
  const clusters = isRecord(value.node_clusters)
    ? Object.values(value.node_clusters)
    : [];
  return (
    positions.every(
      (point) =>
        Array.isArray(point) &&
        point.length === 3 &&
        point.every((item) => isNumber(item)),
    ) &&
    neighbors.every(
      (items) =>
        Array.isArray(items) &&
        items.every(
          (item) => isRecord(item) && isString(item.id) && isNumber(item.score),
        ),
    ) &&
    clusters.every(isString)
  );
}

function sameIds(value: unknown, expected: ReadonlySet<string>): boolean {
  return (
    isRecord(value) &&
    Object.keys(value).length === expected.size &&
    Object.keys(value).every((id) => expected.has(id))
  );
}

function coreIds(core: RecordValue): Set<string> {
  return new Set([
    ...(core.topics as RecordValue[]).map((item) => `topic:${String(item.id)}`),
    ...(core.tricks as RecordValue[]).map((item) => `trick:${String(item.id)}`),
    ...(core.ideas as RecordValue[]).map((item) => String(item.id)),
  ]);
}

function coreScope(core: RecordValue): LayoutScope {
  const ids = coreIds(core);
  const asset = isRecord(core.paper_asset) ? core.paper_asset : {};
  const meta = isRecord(core.meta) ? core.meta : {};
  const ideas = core.ideas as unknown[];
  const topics = core.topics as unknown[];
  const tricks = core.tricks as unknown[];
  const paper = Number(meta.research_entry_count);
  const context = Number(meta.context_entry_count);
  return {
    ids,
    nodeCount: ids.size + Number(asset.paper_count),
    fitCount: paper + ideas.length,
    cohorts: {
      all: ids.size + Number(asset.paper_count),
      paper,
      context,
      idea: ideas.length,
      taxonomy: topics.length + tricks.length,
    },
  };
}

function metaError(value: unknown): string | null {
  if (!isRecord(value) || !hasOnlyKeys(value, META_KEYS)) return "invalid metadata";
  if (!isString(value.generated_at) || !isString(value.notice)) {
    return "invalid metadata text";
  }
  const counts = [
    value.paper_count,
    value.research_entry_count,
    value.context_entry_count,
    value.repo_count,
    value.idea_count,
    value.full_reading_count,
    value.extracted_fulltext_count,
  ];
  return counts.every(
    (count) => isNumber(count) && Number.isInteger(count) && count >= 0,
  )
    ? null
    : "invalid metadata count";
}

function assetError(value: unknown): string | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ASSET_KEYS)) {
    return "invalid paper asset metadata";
  }
  const match = isString(value.path) ? PAPER_PATH.exec(value.path) : null;
  return value.schema_version === 1 &&
    match?.[1] === value.sha256 &&
    isNumber(value.bytes) &&
    Number.isInteger(value.bytes) &&
    value.bytes > 0 &&
    isNumber(value.paper_count) &&
    Number.isInteger(value.paper_count) &&
    value.paper_count >= 0
    ? null
    : "invalid paper asset contract";
}

function routeError(core: RecordValue): string | null {
  const topicIds = new Set(
    (core.topics as RecordValue[]).map((item) => String(item.id)),
  );
  const trickIds = new Set(
    (core.tricks as RecordValue[]).map((item) => String(item.id)),
  );
  const ideas = core.ideas as RecordValue[];
  const badTopic = ideas.some((idea) =>
    (idea.topic_ids as string[]).some((id) => !topicIds.has(id)),
  );
  const badTrick = ideas.some((idea) =>
    (idea.trick_ids as string[]).some((id) => !trickIds.has(id)),
  );
  return badTopic || badTrick ? "unknown idea taxonomy reference" : null;
}

export function coreError(value: unknown): string | null {
  if (!isRecord(value) || !hasOnlyKeys(value, CORE_KEYS)) return "invalid core shape";
  if (value.schema_version !== 2 || "personal_sources" in value) {
    return "invalid core version";
  }
  const metadataError = metaError(value.meta);
  if (metadataError) return metadataError;
  const paperError = assetError(value.paper_asset);
  if (paperError) return paperError;
  if (
    !Array.isArray(value.topics) ||
    !value.topics.every(isTaxon) ||
    !Array.isArray(value.tricks) ||
    !value.tricks.every(isTaxon) ||
    !Array.isArray(value.repos) ||
    value.repos.length > 0 ||
    !Array.isArray(value.ideas) ||
    !isCoverage(value.coverage) ||
    !isRecord(value.layout)
  ) {
    return "invalid core content";
  }
  const meta = value.meta as RecordValue;
  const asset = value.paper_asset as RecordValue;
  if (
    meta.paper_count !== asset.paper_count ||
    Number(meta.research_entry_count) + Number(meta.context_entry_count) !==
      meta.paper_count ||
    meta.repo_count !== 0
  ) {
    return "inconsistent core counts";
  }
  if (!value.ideas.every(isCoreIdea)) {
    return "invalid core idea";
  }
  const idCount = value.topics.length + value.tricks.length + value.ideas.length;
  if (coreIds(value).size !== idCount) return "duplicate core graph node IDs";
  const semanticError = layoutError(value.layout, coreScope(value));
  if (semanticError) return semanticError;
  const hierarchyError = portfolioError(value.ideas);
  if (hierarchyError) return hierarchyError;
  return routeError(value);
}

export function bundleError(value: unknown, asset: PaperAsset): string | null {
  if (!isRecord(value)) {
    return "invalid paper bundle shape";
  }
  const versionIsValid =
    (value.schema_version === 1 && hasOnlyKeys(value, LEGACY_BUNDLE_KEYS)) ||
    (value.schema_version === 2 && hasOnlyKeys(value, BUNDLE_KEYS));
  const layout = value.layout;
  const layoutIsValid = shardLayout(layout);
  const paperIds = new Set(
    Array.isArray(value.papers)
      ? value.papers.flatMap((paper) =>
          isRecord(paper) && isString(paper.id) ? [paper.id] : [],
        )
      : [],
  );
  return versionIsValid &&
    Array.isArray(value.papers) &&
    value.papers.length === asset.paper_count &&
    (value.schema_version === 1 || Array.isArray(value.ideas)) &&
    layoutIsValid &&
    LAYOUT_MAPS.every((field) => sameIds(layout[field], paperIds))
    ? null
    : "invalid paper bundle contract";
}

export function stageAtlas(core: AtlasCore): AtlasPreview {
  const { schema_version: _version, paper_asset: _asset, ...atlas } = core;
  return { ...atlas, papers: [], complete: false };
}

function mergeLayout(
  core: AtlasCore["layout"],
  shard: AcceptedPaperBundle["layout"],
  paperIds: ReadonlySet<string>,
): Atlas["layout"] {
  if (!core) return core;
  const merged = { ...core } as Record<string, unknown>;
  const coreRecord = core as unknown as Record<string, unknown>;
  if (!shard) {
    if (paperIds.size > 0) throw new Error("Paper layout shard is missing");
    const ownsPaper = LAYOUT_MAPS.some(
      (field) =>
        isRecord(coreRecord[field]) &&
        Object.keys(coreRecord[field]).some((id) => paperIds.has(id)),
    );
    if (ownsPaper) throw new Error("Paper layout shard is missing");
    return core;
  }
  for (const field of LAYOUT_MAPS) {
    const extra = shard[field];
    if (!extra) continue;
    const base = isRecord(coreRecord[field]) ? coreRecord[field] : {};
    const overlap = Object.keys(extra).find((id) => id in base);
    if (overlap) throw new Error(`Paper layout overlaps core at ${field}:${overlap}`);
    if (
      Object.keys(extra).some((id) => !paperIds.has(id)) ||
      Object.keys(base).some((id) => paperIds.has(id))
    ) {
      throw new Error(`Paper layout ownership is invalid at ${field}`);
    }
    merged[field] = { ...base, ...extra };
  }
  return merged as Atlas["layout"];
}

export function mergeAtlas(core: AtlasCore, bundle: AcceptedPaperBundle): Atlas {
  const staged = stageAtlas(core);
  const { complete: _complete, ...atlasCore } = staged;
  const atlas = {
    ...atlasCore,
    papers: bundle.papers,
    ideas: [...atlasCore.ideas, ...(bundle.schema_version === 2 ? bundle.ideas : [])],
    ...(bundle.schema_version === 2 && bundle.idea_layout
      ? { idea_layout: bundle.idea_layout }
      : {}),
    layout: mergeLayout(
      staged.layout,
      bundle.layout,
      new Set(bundle.papers.map((paper) => paper.id)),
    ),
  };
  if (atlas.layout) {
    const error = layoutError(atlas.layout, atlasScope(atlas));
    if (error) throw new Error(`Merged atlas layout is invalid: ${error}`);
  }
  if (!isAtlasPayload(atlas)) throw new Error("Merged atlas has an invalid shape");
  return atlas;
}
