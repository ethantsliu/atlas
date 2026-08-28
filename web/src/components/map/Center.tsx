import { useCallback, type MouseEvent } from "react";
import { layoutTime } from "../../hooks/layout";
import {
  nodeCamera,
  pad2d,
  pad3d,
  read2d,
  read3d,
  show2d,
  show3d,
} from "../../lib/camera";
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

function safeOffset(button: HTMLButtonElement): number {
  const wrap = button.closest(".graph-wrap");
  const toolbar = button.closest(".graph-toolbar");
  const canvas = wrap?.querySelector("canvas");
  if (!toolbar || !canvas) return 0;
  const toolbarBox = toolbar.getBoundingClientRect();
  const canvasBox = canvas.getBoundingClientRect();
  const center = canvasBox.top + canvasBox.height / 2;
  return Math.max(0, toolbarBox.bottom + 12 - center);
}

export function CenterButton({
  graphRef,
  fallbackRef,
  height,
  mode,
  selected,
}: CenterProps) {
  const center = useCallback(
    (event: MouseEvent<HTMLButtonElement>) => {
      const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      const duration = layoutTime(Boolean(reduced), 350);
      if (mode === "3d") {
        const current = read3d(graphRef.current);
        const next = current && nodeCamera(current, selected);
        if (next) {
          const padded = pad3d(next, height, safeOffset(event.currentTarget));
          show3d(graphRef.current, padded, duration);
        }
        return;
      }
      const current = read2d(fallbackRef.current, height);
      const next = current && nodeCamera(current, selected);
      if (next) {
        const padded = pad2d(next, height, safeOffset(event.currentTarget));
        show2d(fallbackRef.current, padded, height, duration);
      }
    },
    [fallbackRef, graphRef, height, mode, selected],
  );

  return (
    <button className="view-reset" type="button" onClick={center}>
      Center selected
    </button>
  );
}
