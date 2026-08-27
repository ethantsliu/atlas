import { useCallback, useEffect, useRef, useState } from "react";
import type { GraphRef } from "../components/map/Driver";
import type { GraphNode } from "../types";
import { bindChange } from "./control";
import { nodeDepth } from "./points";

export type CoreTip = { depth: number; node: GraphNode; x: number; y: number };

export function useCore(graphRef: GraphRef) {
  const [tip, setTip] = useState<CoreTip | null>(null);
  const cursor = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const graph = graphRef.current;
    const canvas = graph?.renderer().domElement;
    const move = (event: PointerEvent) => {
      const rect = canvas?.getBoundingClientRect();
      if (!rect) return;
      cursor.current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };
    canvas?.addEventListener("pointermove", move, true);
    const drop = bindChange(graph?.controls?.(), () => setTip(null));
    return () => {
      canvas?.removeEventListener("pointermove", move, true);
      drop();
    };
  }, [graphRef]);

  const hover = useCallback(
    (node: GraphNode | null) => {
      setTip(
        node
          ? { depth: nodeDepth(graphRef.current, node), node, ...cursor.current }
          : null,
      );
    },
    [graphRef],
  );
  return { hover, tip };
}
