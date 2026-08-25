import { useEffect } from "react";
import type { ForceGraphMethods } from "react-force-graph-3d";
import type { GraphLink, GraphNode } from "../types";
import type { GraphRef } from "../components/map/Driver";

export function usePixel(graphRef: GraphRef, cap: number) {
  useEffect(() => {
    const api = graphRef.current as ForceGraphMethods<GraphNode, GraphLink> | undefined;
    api?.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, cap));
  }, [cap, graphRef]);
}
