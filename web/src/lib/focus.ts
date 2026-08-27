import { createGraphNodes } from "./graph";
import type { AtlasRead } from "./payload";
import type { CloudData, CloudPick, CloudRelation } from "./cloud";
import type { GraphData, GraphNode } from "../types";

export type CloudMark = {
  center: [number, number, number];
  targets: { point: [number, number, number]; score: number }[];
};

export type CloudFocus = { graph: GraphData; mark: CloudMark };

function fixedNode(node: GraphNode): GraphNode | null {
  const x = node.sx ?? node.x;
  const y = node.sy ?? node.y;
  const z = node.sz ?? node.z;
  if (![x, y, z].every(Number.isFinite)) return null;
  return { ...node, x, y, z, fx: x, fy: y, fz: z } as GraphNode;
}

export function focusCloud(
  atlas: AtlasRead,
  cloud: CloudData,
  pick: CloudPick,
  relation: CloudRelation | null,
): CloudFocus | null {
  const offset = pick.index * 3;
  const center = Array.from(cloud.positions.slice(offset, offset + 3)) as [
    number,
    number,
    number,
  ];
  if (center.length !== 3 || !center.every(Number.isFinite)) return null;
  const nodes = new Map(
    createGraphNodes(atlas, 1)
      .map(fixedNode)
      .filter((node): node is GraphNode => Boolean(node))
      .map((node) => [node.id, node]),
  );
  const selected = (relation?.neighbors ?? []).map((entry) => ({
    entry,
    node: nodes.get(entry.id),
  }));
  if (selected.some(({ node }) => !node)) return null;
  const anchors = selected.map(({ node }) => node!);
  return {
    graph: { nodes: anchors, links: [] },
    mark: {
      center,
      targets: selected.map(({ entry, node }) => ({
        point: [node!.x!, node!.y!, node!.z!],
        score: entry.score,
      })),
    },
  };
}
