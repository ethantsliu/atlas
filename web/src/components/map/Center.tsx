import { useCallback } from "react";
import { layoutTime } from "../../hooks/layout";
import { nodeCamera, read2d, read3d, show2d, show3d } from "../../lib/camera";
import type { GraphNode } from "../../types";
import type { GraphRef } from "./Driver";
import type { FallbackRef } from "./Fallback";
import type { RenderMode } from "./Controls";

type CenterProps = {
  graphRef: GraphRef;
  fallbackRef: FallbackRef;
  height: number;
  mode: RenderMode;
  selected: GraphNode;
};

export function CenterButton({
  graphRef,
  fallbackRef,
  height,
  mode,
  selected,
}: CenterProps) {
  const center = useCallback(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const duration = layoutTime(Boolean(reduced), 350);
    if (mode === "3d") {
      const current = read3d(graphRef.current);
      const next = current && nodeCamera(current, selected);
      if (next) show3d(graphRef.current, next, duration);
      return;
    }
    const current = read2d(fallbackRef.current, height);
    const next = current && nodeCamera(current, selected);
    if (next) show2d(fallbackRef.current, next, height, duration);
  }, [fallbackRef, graphRef, height, mode, selected]);

  return (
    <button className="view-reset" type="button" onClick={center}>
      Center selected
    </button>
  );
}
