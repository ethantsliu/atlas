import { useMemo } from "react";
import type { LayoutMode } from "./layout";
import { limitGraph, renderCap, renderIds } from "../lib/lod";
import type { QualityTier } from "../lib/quality";
import type { GraphData } from "../types";

export type SceneState = {
  graph: GraphData;
  ids: Set<string> | null;
  simple: boolean;
};

export function useScene(
  graph: GraphData,
  layout: LayoutMode,
  tier: QualityTier,
  selectedId?: string,
): SceneState {
  const ids = useMemo(() => {
    const cap = renderCap(tier);
    return renderIds(graph.nodes, layout === "connections" ? Math.min(cap, 60) : cap);
  }, [graph.nodes, layout, tier]);
  const extra = selectedId && !ids?.has(selectedId) ? selectedId : undefined;
  const scene = useMemo(() => limitGraph(graph, ids, extra), [extra, graph, ids]);
  return { graph: scene, ids, simple: graph.nodes.length >= 1_000 };
}
