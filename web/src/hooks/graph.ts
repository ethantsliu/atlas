import { useMemo, useRef } from "react";
import { stableGraph } from "../lib/graph";
import type { GraphData, GraphNode } from "../types";

export function useGraph(graph: GraphData): GraphData {
  const cache = useRef(new Map<string, GraphNode>());
  return useMemo(() => stableGraph(graph, cache.current), [graph]);
}
