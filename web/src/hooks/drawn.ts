import { useMemo } from "react";
import { renderCap, renderIds } from "../lib/lod";
import type { GraphData } from "../types";
import type { LayoutMode } from "./layout";
import { useQuality } from "./quality";

export function useDrawn(
  graph: GraphData,
  width: number,
  height: number,
  layout: LayoutMode,
  selected?: string,
): number {
  const quality = useQuality(graph.nodes.length, width, height);
  return useMemo(() => {
    const cap = renderCap(quality.tier);
    const ids = renderIds(
      graph.nodes,
      layout === "connections" ? Math.min(cap, 60) : cap,
      [selected],
    );
    return ids?.size ?? graph.nodes.length;
  }, [graph.nodes, layout, quality.tier, selected]);
}
