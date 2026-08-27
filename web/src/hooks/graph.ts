import { useMemo, useRef } from "react";
import { graphKey, stableGraph } from "../lib/graph";
import type { GraphData, GraphNode } from "../types";

export type GraphState = { graph: GraphData; key: string };

export function keepGraph(
  graph: GraphData,
  prior: GraphState | undefined,
  cache: Map<string, GraphNode>,
): GraphState {
  const next = stableGraph(graph, cache);
  const key = graphKey(next);
  return prior?.key === key ? prior : { graph: next, key };
}

export function useGraph(graph: GraphData): GraphData {
  const cache = useRef(new Map<string, GraphNode>());
  const prior = useRef<GraphState>();
  return useMemo(() => {
    prior.current = keepGraph(graph, prior.current, cache.current);
    return prior.current.graph;
  }, [graph]);
}
