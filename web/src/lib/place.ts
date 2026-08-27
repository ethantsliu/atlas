import type { Atlas, IdeaLayout, SemanticLayout } from "../types";
import { hasOnlyKeys, isNumber, isRecord, isString } from "./guards";

const HASH = /^[0-9a-f]{64}$/;
const KEYS = new Set([
  "schema_version",
  "method",
  "base_method",
  "base_node_count",
  "base_sha256",
  "input_sha256",
  "node_count",
  "positions",
  "neighbors",
  "node_clusters",
]);

function sameIds(value: unknown, ids: ReadonlySet<string>): boolean {
  return (
    isRecord(value) &&
    Object.keys(value).length === ids.size &&
    Object.keys(value).every((id) => ids.has(id))
  );
}

export function placeError(
  value: unknown,
  ideas: Atlas["ideas"],
  layout: SemanticLayout,
): string | null {
  const fitted = new Set(Object.keys(layout.positions));
  const derived = new Set(ideas.map((idea) => idea.id).filter((id) => !fitted.has(id)));
  if (derived.size === 0 && value == null) return null;
  if (!isRecord(value) || !hasOnlyKeys(value, KEYS)) return "invalid idea layout";
  if (
    value.schema_version !== 1 ||
    value.method !== "support-centroid-80-20-3d-v1" ||
    value.base_method !== layout.method ||
    value.base_node_count !== layout.node_count ||
    !isString(value.base_sha256) ||
    !HASH.test(value.base_sha256) ||
    !isString(value.input_sha256) ||
    !HASH.test(value.input_sha256) ||
    value.node_count !== derived.size ||
    !sameIds(value.positions, derived) ||
    !sameIds(value.neighbors, derived) ||
    !sameIds(value.node_clusters, derived)
  ) {
    return "invalid idea layout";
  }
  const baseIds = new Set(Object.keys(layout.positions));
  const positions = value.positions as IdeaLayout["positions"];
  const neighbors = value.neighbors as IdeaLayout["neighbors"];
  const clusters = value.node_clusters as IdeaLayout["node_clusters"];
  const clusterIds = new Set(layout.clusters.map((cluster) => cluster.id));
  const occupied = new Set(
    Object.values(layout.positions).map((point) => point.join()),
  );
  for (const id of derived) {
    const point = positions[id];
    const pointKey = Array.isArray(point) ? point.join() : "";
    if (
      !Array.isArray(point) ||
      point.length !== 3 ||
      !point.every(isNumber) ||
      occupied.has(pointKey) ||
      !Array.isArray(neighbors[id]) ||
      neighbors[id].length === 0 ||
      neighbors[id].length > 8 ||
      new Set(neighbors[id]).size !== neighbors[id].length ||
      !neighbors[id].every((target) => isString(target) && baseIds.has(target)) ||
      !isString(clusters[id]) ||
      !clusterIds.has(clusters[id])
    ) {
      return "invalid idea placement";
    }
    occupied.add(pointKey);
  }
  return null;
}
