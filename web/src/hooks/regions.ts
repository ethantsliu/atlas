import { useCallback, useEffect, useRef, useState } from "react";
import type { ForceGraphMethods } from "react-force-graph-3d";
import { Vector3 } from "three";
import {
  viewRegions,
  type ClusterSet,
  type RegionBox,
  type RegionPoint,
} from "../lib/clusters";
import type { QualityProfile } from "../lib/quality";
import type { GraphData, GraphLink, GraphNode } from "../types";
import type { GraphRef } from "../components/map/Driver";

type RegionInput = {
  graph: GraphData;
  graphRef: GraphRef;
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

type RegionResult = RegionState & {
  project: () => void;
  markFit: () => void;
};

type ControlApi = {
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
};

function labelBox(api: ForceGraphMethods<GraphNode, GraphLink>, node: GraphNode) {
  if (node.x == null || node.y == null || node.z == null) return null;
  const point = api.graph2ScreenCoords(node.x, node.y, node.z);
  return {
    left: point.x - 120,
    right: point.x + 120,
    top: point.y - 34,
    bottom: point.y + 52,
  };
}

export function useRegions({
  graph,
  graphRef,
  clusters,
  active,
  quality,
  enabled,
}: RegionInput): RegionResult {
  const [state, setState] = useState<RegionState>({
    points: [],
    scale: 1,
    reserved: [],
  });
  const fitRef = useRef(0);
  const frameRef = useRef<number>();
  const runProject = useCallback(() => {
    if (!enabled) return;
    const api = graphRef.current as ForceGraphMethods<GraphNode, GraphLink> | undefined;
    if (!api) return;
    const camera = api.camera();
    const distance = camera.position.length() || 1;
    const regions = viewRegions(clusters, graph.nodes).filter(
      (region) => region.count >= quality.clusterMinNodes,
    );
    const points = regions.map((region) => {
      const [x, y, z] = region.centroid;
      const screen = api.graph2ScreenCoords(x, y, z);
      return {
        region,
        x: screen.x,
        y: screen.y,
        depth: new Vector3(x, y, z).project(camera).z,
      };
    });
    const seen = new Set<string>();
    const reserved = active.flatMap((node) => {
      if (!node || seen.has(node.id)) return [];
      seen.add(node.id);
      const box = labelBox(api, node);
      return box ? [box] : [];
    });
    setState({
      points,
      scale: fitRef.current > 0 ? fitRef.current / distance : 1,
      reserved,
    });
  }, [active, clusters, enabled, graph.nodes, graphRef, quality.clusterMinNodes]);

  const project = useCallback(() => {
    if (!enabled || frameRef.current != null) return;
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = undefined;
      runProject();
    });
  }, [enabled, runProject]);

  const markFit = useCallback(() => {
    const api = graphRef.current as ForceGraphMethods<GraphNode, GraphLink> | undefined;
    fitRef.current = api?.camera().position.length() ?? 0;
    project();
  }, [graphRef, project]);

  useEffect(() => {
    const api = graphRef.current as ForceGraphMethods<GraphNode, GraphLink> | undefined;
    const controls = api?.controls() as ControlApi | undefined;
    if (!controls || !enabled) return;
    controls.addEventListener("change", project);
    project();
    return () => controls.removeEventListener("change", project);
  }, [enabled, graphRef, project]);

  useEffect(
    () => () => {
      if (frameRef.current != null) window.cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  return { ...state, project, markFit };
}
