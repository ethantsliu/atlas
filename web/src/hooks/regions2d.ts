import { useCallback, useState, type MutableRefObject } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import {
  viewRegions,
  type ClusterSet,
  type RegionBox,
  type RegionPoint,
} from "../lib/clusters";
import type { QualityProfile } from "../lib/quality";
import type { GraphData, GraphLink, GraphNode } from "../types";

type Input = {
  graph: GraphData;
  graphRef: MutableRefObject<ForceGraphMethods<GraphNode, GraphLink> | undefined>;
  clusters: ClusterSet;
  active: readonly (GraphNode | null)[];
  quality: QualityProfile;
  enabled: boolean;
};

type RegionState = {
  points: RegionPoint[];
  scale: number;
  reserved: RegionBox[];
};

function labelBox(api: ForceGraphMethods<GraphNode, GraphLink>, node: GraphNode) {
  if (node.x == null || node.y == null) return null;
  const point = api.graph2ScreenCoords(node.x, node.y);
  return {
    left: point.x - 120,
    right: point.x + 120,
    top: point.y - 34,
    bottom: point.y + 52,
  };
}

export function useRegions2d({
  graph,
  graphRef,
  clusters,
  active,
  quality,
  enabled,
}: Input) {
  const [state, setState] = useState<RegionState>({
    points: [],
    scale: 1,
    reserved: [],
  });
  const project = useCallback(
    (scale = 1) => {
      if (!enabled) return;
      const api = graphRef.current;
      if (!api) return;
      const points = viewRegions(clusters, graph.nodes)
        .filter((region) => region.count >= quality.clusterMinNodes)
        .map((region) => {
          const [x, y] = region.centroid;
          const screen = api.graph2ScreenCoords(x, y);
          return { region, x: screen.x, y: screen.y, depth: 0 };
        });
      const seen = new Set<string>();
      const reserved = active.flatMap((node) => {
        if (!node || seen.has(node.id)) return [];
        seen.add(node.id);
        const box = labelBox(api, node);
        return box ? [box] : [];
      });
      setState({ points, scale, reserved });
    },
    [active, clusters, enabled, graph.nodes, graphRef, quality.clusterMinNodes],
  );
  return { ...state, project };
}
