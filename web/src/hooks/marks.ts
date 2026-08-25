import { useEffect, useMemo, useRef } from "react";
import type { Theme } from "./theme";
import { markNode } from "../lib/scene";
import type { GraphNode } from "../types";
import type { GraphRef } from "../components/map/Driver";

type MarkInput = {
  graphRef: GraphRef;
  nodes: GraphNode[];
  selected: GraphNode | null;
  hovered: GraphNode | null;
  theme: Theme;
  detail: number;
  simple: boolean;
};

export function useMarks(input: MarkInput): void {
  const activeRef = useRef(new Set<string>());
  const nodeById = useMemo(
    () => new Map(input.nodes.map((node) => [node.id, node])),
    [input.nodes],
  );

  useEffect(() => {
    const active = new Set(
      [input.selected?.id, input.hovered?.id].filter((id): id is string => Boolean(id)),
    );
    const changed = new Set([...activeRef.current, ...active]);
    for (const id of changed) {
      const node = nodeById.get(id);
      if (!node) continue;
      markNode(node, active.has(id), input.theme, input.detail, input.simple);
    }
    activeRef.current = active;
    input.graphRef.current?.refresh();
  }, [
    input.detail,
    input.graphRef,
    input.hovered?.id,
    input.selected?.id,
    input.simple,
    input.theme,
    nodeById,
  ]);
}
