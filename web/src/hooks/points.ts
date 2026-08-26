import { useEffect } from "react";
import type { GraphRef } from "../components/map/Driver";
import type { CloudData } from "../lib/cloud";
import { buildCloud } from "../lib/swarm";
import type { Theme } from "./theme";

export function usePoints(
  graphRef: GraphRef,
  data: CloudData | null,
  theme: Theme,
): void {
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !data || data.scopes.length === 0) return;
    const points = buildCloud(data, theme);
    graph.scene().add(points);
    return () => {
      graph.scene().remove(points);
      points.geometry.dispose();
      points.material.dispose();
    };
  }, [data, graphRef, theme]);
}
