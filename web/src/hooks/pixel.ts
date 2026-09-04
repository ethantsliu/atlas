import { useLayoutEffect } from "react";
import type { ForceGraphMethods } from "react-force-graph-3d";
import type { GraphLink, GraphNode } from "../types";
import type { GraphRef } from "../components/map/Driver";

export function usePixel(graphRef: GraphRef, cap: number) {
  useLayoutEffect(() => {
    const api = graphRef.current as ForceGraphMethods<GraphNode, GraphLink> | undefined;
    if (!api) return;
    const ratio = Math.min(window.devicePixelRatio || 1, cap);
    api.renderer().setPixelRatio(ratio);
    // ForceGraph renders through an EffectComposer with independent targets.
    // Resize both stores so the dense cap actually releases supersampled
    // color/depth buffers rather than shrinking only the canvas backing store.
    api.postProcessingComposer().setPixelRatio(ratio);
  }, [cap, graphRef]);
}
