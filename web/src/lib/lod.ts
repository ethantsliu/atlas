import type { QualityTier } from "./quality";
import { graphEndpointId } from "./graph";
import type { GraphData, GraphNode } from "../types";

const CAPS: Record<QualityTier, number> = {
  high: 480,
  balanced: 240,
  low: 120,
};

function hashId(id: string): number {
  let value = 2_166_136_261;
  for (let index = 0; index < id.length; index += 1) {
    value ^= id.charCodeAt(index);
    value = Math.imul(value, 16_777_619);
  }
  return value >>> 0;
}

export function renderCap(tier: QualityTier): number {
  return CAPS[tier];
}

export function renderIds(
  nodes: GraphNode[],
  cap: number,
  active: readonly (string | undefined)[] = [],
): Set<string> | null {
  const papers = nodes.filter((node) => node.kind === "paper");
  if (papers.length <= cap) return null;
  const chosen = papers
    .map((node) => ({ id: node.id, rank: hashId(node.id) }))
    .sort((left, right) => left.rank - right.rank)
    .slice(0, cap)
    .map((item) => item.id);
  return new Set([
    ...nodes.filter((node) => node.kind !== "paper").map((node) => node.id),
    ...chosen,
    ...active.filter((id): id is string => Boolean(id)),
  ]);
}

export function limitGraph(
  graph: GraphData,
  ids: Set<string> | null,
  extra?: string,
): GraphData {
  if (!ids) return graph;
  const visible = extra && !ids.has(extra) ? new Set([...ids, extra]) : ids;
  return {
    nodes: graph.nodes.filter((node) => visible.has(node.id)),
    links: graph.links.filter(
      (link) =>
        visible.has(graphEndpointId(link.source)) &&
        visible.has(graphEndpointId(link.target)),
    ),
  };
}
