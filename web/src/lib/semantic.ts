import type { Atlas, SemanticLayout } from "../types";
import { hasOnlyKeys, isNumber, isRecord, isString } from "./guards";

const HASH = /^[0-9a-f]{64}$/;
const MODEL_HASH = "1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef";
const MAP_KEYS = ["positions", "neighbors", "node_clusters"] as const;
const LAYOUT_KEYS = new Set([
  "schema_version",
  "model",
  "embedding",
  "method",
  "reducer",
  "input_sha256",
  "node_count",
  "quality",
  "neighbor_count",
  "neighbors",
  "mix_quality",
  "cluster_method",
  "cluster_kind",
  "cluster_quality",
  "clusters",
  "node_clusters",
  "positions",
]);
const EMBED_KEYS = new Set([
  "provider",
  "api",
  "model",
  "artifact_sha256",
  "dimensions",
  "context_length",
  "metric",
  "runtime",
  "text_schema",
  "truncate",
  "input_sha256",
  "vector_sha256",
]);
const REDUCER_KEYS = new Set([
  "name",
  "dimensions",
  "neighbors",
  "min_dist",
  "metric",
  "random_seed",
  "repulsion_strength",
  "negative_sample_rate",
  "scale_percentile",
  "clip",
  "extent",
]);
const QUALITY_KEYS = new Set([
  "k",
  "trustworthiness",
  "knn_recall",
  "thresholds",
  "alias_policy",
  "cohort_policy",
  "cohorts",
]);
const COHORT_KEYS = new Set(["all", "paper", "context", "idea", "taxonomy"]);
const COHORT_VALUE_KEYS = new Set([
  "node_count",
  "trustworthiness",
  "knn_recall",
  "thresholds",
]);
const THRESHOLD_KEYS = new Set(["trustworthiness", "knn_recall"]);
const COHORT_THRESHOLDS: Record<
  keyof LayoutScope["cohorts"],
  { trustworthiness: number; knn_recall: number }
> = {
  all: { trustworthiness: 0.9, knn_recall: 0.25 },
  paper: { trustworthiness: 0.9, knn_recall: 0.25 },
  context: { trustworthiness: 0, knn_recall: 0 },
  idea: { trustworthiness: 0.95, knn_recall: 0.4 },
  taxonomy: { trustworthiness: 0.88, knn_recall: 0.33 },
};
const MIX_KEYS = new Set([
  "kind",
  "neighbor_count",
  "semantic_routes",
  "projected_routes",
  "position_eta_squared",
  "exact_coordinate_duplicates",
  "thresholds",
]);
const ROUTE_NAMES = ["topic", "trick", "combined"] as const;
const ROUTE_KINDS = new Set(ROUTE_NAMES);
const ROUTE_KEYS = new Set(["node_count", "precision", "hit_rate"]);
const MIX_THRESHOLD_KEYS = new Set([
  "routes",
  "max_position_eta_squared",
  "max_exact_coordinate_duplicates",
]);
const ROUTE_GATE_KEYS = new Set(["precision", "hit_rate"]);
const ROUTE_GATES = {
  semantic: {
    topic: { precision: 0.2, hit_rate: 0.75 },
    trick: { precision: 0.2, hit_rate: 0.75 },
    combined: { precision: 0.2, hit_rate: 0.75 },
  },
  projected: {
    topic: { precision: 0.2, hit_rate: 0.5 },
    trick: { precision: 0.2, hit_rate: 0.5 },
    combined: { precision: 0.3, hit_rate: 0.5 },
  },
} as const;
const CLUSTER_KEYS = new Set([
  "inertia",
  "mean_inertia",
  "silhouette",
  "stability_ari",
  "fit_count",
  "silhouette_count",
  "thresholds",
  "min_count",
  "max_share",
]);
const REGION_KEYS = new Set([
  "id",
  "label",
  "label_source",
  "label_similarity",
  "centroid",
  "count",
  "radius",
  "medoid",
  "spread",
  "terms",
]);

export type LayoutScope = {
  ids: ReadonlySet<string>;
  allIds?: ReadonlySet<string>;
  nodeCount: number;
  fitCount: number;
  cohorts: Record<"all" | "paper" | "context" | "idea" | "taxonomy", number>;
};

export function atlasScope(
  atlas: Pick<Atlas, "topics" | "tricks" | "papers" | "ideas">,
): LayoutScope {
  const ids = new Set([
    ...atlas.topics.map((item) => `topic:${item.id}`),
    ...atlas.tricks.map((item) => `trick:${item.id}`),
    ...atlas.papers.map((item) => item.id),
    ...atlas.ideas.map((item) => item.id),
  ]);
  const context = atlas.papers.filter(
    (paper) => paper.record_kind === "non_paper_context",
  ).length;
  const paper = atlas.papers.length - context;
  return {
    ids,
    allIds: ids,
    nodeCount: ids.size,
    fitCount: paper + atlas.ideas.length,
    cohorts: {
      all: ids.size,
      paper,
      context,
      idea: atlas.ideas.length,
      taxonomy: atlas.topics.length + atlas.tricks.length,
    },
  };
}

function exactKeys(
  value: unknown,
  keys: ReadonlySet<string>,
): value is Record<string, unknown> {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, keys) &&
    Object.keys(value).length === keys.size
  );
}

function isHash(value: unknown): value is string {
  return isString(value) && HASH.test(value);
}

function isInt(value: unknown): value is number {
  return isNumber(value) && Number.isInteger(value) && value >= 0;
}

function isUnit(value: unknown): value is number {
  return isNumber(value) && value >= 0 && value <= 1;
}

function isPoint(value: unknown): value is [number, number, number] {
  return Array.isArray(value) && value.length === 3 && value.every(isNumber);
}

function sameIds(
  value: unknown,
  ids: ReadonlySet<string>,
): value is Record<string, unknown> {
  return (
    isRecord(value) &&
    Object.keys(value).length === ids.size &&
    Object.keys(value).every((id) => ids.has(id))
  );
}

function embeddingError(value: unknown): string | null {
  if (!exactKeys(value, EMBED_KEYS)) return "invalid embedding provenance";
  return value.provider === "ollama" &&
    value.api === "embed-v1" &&
    value.model === "all-minilm" &&
    value.artifact_sha256 === MODEL_HASH &&
    value.dimensions === 384 &&
    value.context_length === 256 &&
    value.metric === "cosine" &&
    value.runtime === "ollama-0.13.1" &&
    value.text_schema === "field-budget-v2" &&
    value.truncate === false &&
    isHash(value.input_sha256) &&
    isHash(value.vector_sha256)
    ? null
    : "invalid embedding provenance";
}

function reducerError(value: unknown): string | null {
  if (!exactKeys(value, REDUCER_KEYS)) return "invalid semantic reducer";
  return value.name === "umap" &&
    value.dimensions === 3 &&
    value.neighbors === 32 &&
    value.min_dist === 0.08 &&
    value.metric === "cosine" &&
    value.random_seed === 42 &&
    value.repulsion_strength === 2 &&
    value.negative_sample_rate === 20 &&
    value.scale_percentile === 98 &&
    value.clip === 1.25 &&
    value.extent === 360
    ? null
    : "invalid semantic reducer";
}

function cohortError(value: unknown, scope: LayoutScope): string | null {
  if (!exactKeys(value, COHORT_KEYS)) return "invalid quality cohorts";
  for (const name of Object.keys(scope.cohorts) as Array<
    keyof LayoutScope["cohorts"]
  >) {
    const count = scope.cohorts[name];
    const cohort = value[name];
    const expected = COHORT_THRESHOLDS[name];
    if (
      !exactKeys(cohort, COHORT_VALUE_KEYS) ||
      cohort.node_count !== count ||
      !isUnit(cohort.trustworthiness) ||
      cohort.trustworthiness < expected.trustworthiness ||
      !isUnit(cohort.knn_recall) ||
      cohort.knn_recall < expected.knn_recall ||
      !exactKeys(cohort.thresholds, THRESHOLD_KEYS) ||
      cohort.thresholds.trustworthiness !== expected.trustworthiness ||
      cohort.thresholds.knn_recall !== expected.knn_recall
    ) {
      return "invalid quality cohorts";
    }
  }
  return null;
}

function qualityError(value: unknown, scope: LayoutScope): string | null {
  if (!exactKeys(value, QUALITY_KEYS)) return "invalid layout quality";
  const thresholds = value.thresholds;
  const cohorts = value.cohorts;
  const cohortIssue = cohortError(cohorts, scope);
  if (cohortIssue) return cohortIssue;
  if (!isRecord(cohorts) || !isRecord(cohorts.all)) return "invalid quality cohorts";
  return value.k === 10 &&
    isUnit(value.trustworthiness) &&
    value.trustworthiness >= 0.9 &&
    isUnit(value.knn_recall) &&
    value.knn_recall >= 0.25 &&
    exactKeys(thresholds, THRESHOLD_KEYS) &&
    thresholds.trustworthiness === 0.9 &&
    thresholds.knn_recall === 0.25 &&
    value.alias_policy === "exclude canonical and identical-text aliases" &&
    value.cohort_policy === "research cohorts gated; context reported descriptively" &&
    cohorts.all.trustworthiness === value.trustworthiness &&
    cohorts.all.knn_recall === value.knn_recall
    ? null
    : "invalid layout quality";
}

function neighborError(
  value: unknown,
  scope: LayoutScope,
  count: unknown,
): string | null {
  if (!sameIds(value, scope.ids) || count !== 8) {
    return "invalid semantic neighbors";
  }
  for (const [source, items] of Object.entries(value)) {
    if (!Array.isArray(items) || items.length !== count)
      return "invalid neighbor count";
    const seen = new Set<string>();
    let prior = Infinity;
    for (const item of items) {
      if (
        !exactKeys(item, new Set(["id", "score"])) ||
        !isString(item.id) ||
        !isNumber(item.score) ||
        item.score < -1 ||
        item.score > 1 ||
        item.score > prior ||
        item.id === source ||
        seen.has(item.id) ||
        (scope.allIds != null && !scope.allIds.has(item.id))
      ) {
        return "invalid semantic neighbor";
      }
      seen.add(item.id);
      prior = item.score;
    }
  }
  return null;
}

function routeError(value: unknown, space: keyof typeof ROUTE_GATES): string | null {
  if (!exactKeys(value, ROUTE_KINDS)) return "invalid route diagnostics";
  for (const kind of ROUTE_NAMES) {
    const score = value[kind];
    const gate = ROUTE_GATES[space][kind];
    if (
      !exactKeys(score, ROUTE_KEYS) ||
      !isInt(score.node_count) ||
      score.node_count === 0 ||
      !isUnit(score.precision) ||
      score.precision < gate.precision ||
      !isUnit(score.hit_rate) ||
      score.hit_rate < gate.hit_rate
    ) {
      return "invalid route diagnostics";
    }
  }
  const rows = value as Record<string, { node_count: number }>;
  return rows.combined.node_count === rows.topic.node_count + rows.trick.node_count
    ? null
    : "invalid route diagnostics";
}

function mixError(value: unknown): string | null {
  if (!exactKeys(value, MIX_KEYS)) return "invalid mixing diagnostics";
  const semanticIssue = routeError(value.semantic_routes, "semantic");
  const projectedIssue = routeError(value.projected_routes, "projected");
  if (semanticIssue || projectedIssue) return semanticIssue ?? projectedIssue;
  const thresholds = value.thresholds;
  if (!exactKeys(thresholds, MIX_THRESHOLD_KEYS) || !isRecord(thresholds.routes)) {
    return "invalid mixing thresholds";
  }
  for (const space of ["semantic", "projected"] as const) {
    const routes = thresholds.routes[space];
    if (!exactKeys(routes, ROUTE_KINDS)) return "invalid mixing thresholds";
    for (const kind of ROUTE_NAMES) {
      const gate = routes[kind];
      const expected = ROUTE_GATES[space][kind];
      if (
        !exactKeys(gate, ROUTE_GATE_KEYS) ||
        gate.precision !== expected.precision ||
        gate.hit_rate !== expected.hit_rate
      ) {
        return "invalid mixing thresholds";
      }
    }
  }
  return value.kind === "cross-kind-layout-v1" &&
    value.neighbor_count === 8 &&
    isUnit(value.position_eta_squared) &&
    value.position_eta_squared <= 0.05 &&
    value.exact_coordinate_duplicates === 0 &&
    thresholds.max_position_eta_squared === 0.05 &&
    thresholds.max_exact_coordinate_duplicates === 0
    ? null
    : "invalid mixing diagnostics";
}

function regionError(value: unknown, allIds?: ReadonlySet<string>): string | null {
  if (!exactKeys(value, REGION_KEYS)) return "invalid semantic cluster";
  const terms = value.terms;
  return isString(value.id) &&
    Boolean(value.id) &&
    isString(value.label) &&
    Boolean(value.label) &&
    value.label === value.label.toLocaleLowerCase() &&
    value.label_source === "one-to-one taxonomy match" &&
    isUnit(value.label_similarity) &&
    value.label_similarity >= 0.3 &&
    isPoint(value.centroid) &&
    isInt(value.count) &&
    value.count > 0 &&
    isNumber(value.radius) &&
    value.radius >= 0 &&
    isString(value.medoid) &&
    Boolean(value.medoid) &&
    (allIds == null || allIds.has(value.medoid)) &&
    isNumber(value.spread) &&
    value.spread >= 0 &&
    value.spread <= 2 &&
    Array.isArray(terms) &&
    terms.length > 0 &&
    terms.length <= 5 &&
    terms.every(
      (term) => isString(term) && Boolean(term) && term === term.toLocaleLowerCase(),
    ) &&
    new Set(terms).size === terms.length
    ? null
    : "invalid semantic cluster";
}

function clusterError(
  value: Record<string, unknown>,
  scope: LayoutScope,
): string | null {
  if (
    !Array.isArray(value.clusters) ||
    !exactKeys(value.cluster_quality, CLUSTER_KEYS)
  ) {
    return "invalid semantic clusters";
  }
  const regions = value.clusters;
  if (regions.length === 0) return "invalid semantic clusters";
  for (const region of regions) {
    const issue = regionError(region, scope.allIds);
    if (issue) return issue;
  }
  const ids = new Set(regions.map((region) => region.id as string));
  const labels = new Set(regions.map((region) => region.label as string));
  if (ids.size !== regions.length || labels.size !== regions.length) {
    return "duplicate semantic cluster";
  }
  const assignments = value.node_clusters;
  if (!sameIds(assignments, scope.ids)) return "incomplete cluster map";
  if (!Object.values(assignments).every((id) => isString(id) && ids.has(id))) {
    return "unknown cluster assignment";
  }
  const quality = value.cluster_quality;
  const counts = regions.map((region) => region.count as number);
  const thresholds = quality.thresholds;
  const maxShare = Math.round((Math.max(...counts) / scope.nodeCount) * 1e6) / 1e6;
  if (
    !isNumber(quality.inertia) ||
    quality.inertia < 0 ||
    !isNumber(quality.mean_inertia) ||
    quality.mean_inertia < 0 ||
    !isUnit(quality.silhouette) ||
    !isUnit(quality.stability_ari) ||
    quality.stability_ari < 0.2 ||
    quality.fit_count !== scope.fitCount ||
    quality.silhouette_count !== scope.fitCount ||
    !exactKeys(thresholds, new Set(["silhouette", "stability_ari"])) ||
    thresholds.silhouette !== 0 ||
    thresholds.stability_ari !== 0.2 ||
    quality.min_count !== Math.min(...counts) ||
    quality.max_share !== maxShare
  ) {
    return "invalid cluster quality";
  }
  if (scope.allIds != null) {
    if (counts.reduce((sum, count) => sum + count, 0) !== scope.nodeCount) {
      return "invalid cluster counts";
    }
    for (const region of regions) {
      const assigned = Object.values(assignments).filter(
        (id) => id === region.id,
      ).length;
      if (assigned !== region.count || assignments[region.medoid] !== region.id) {
        return "invalid cluster membership";
      }
    }
  }
  return null;
}

function mapError(value: Record<string, unknown>, scope: LayoutScope): string | null {
  if (!MAP_KEYS.every((key) => sameIds(value[key], scope.ids))) {
    return "incomplete semantic layout maps";
  }
  if (!isRecord(value.positions) || !Object.values(value.positions).every(isPoint)) {
    return "invalid semantic positions";
  }
  return neighborError(value.neighbors, scope, value.neighbor_count);
}

export function layoutError(value: unknown, scope: LayoutScope): string | null {
  if (!exactKeys(value, LAYOUT_KEYS)) return "invalid semantic layout shape";
  if (
    value.schema_version !== 3 ||
    value.model !== "all-minilm" ||
    value.method !== "embedding-umap-3d-v1" ||
    !isHash(value.input_sha256) ||
    value.node_count !== scope.nodeCount ||
    value.cluster_method !== "embedding-normalized-kmeans-v1" ||
    value.cluster_kind !== "coarse embedding neighborhoods"
  ) {
    return "invalid semantic layout contract";
  }
  return (
    embeddingError(value.embedding) ??
    reducerError(value.reducer) ??
    qualityError(value.quality, scope) ??
    mapError(value, scope) ??
    mixError(value.mix_quality) ??
    clusterError(value, scope)
  );
}

export function isLayout(value: unknown, scope: LayoutScope): value is SemanticLayout {
  return layoutError(value, scope) === null;
}
