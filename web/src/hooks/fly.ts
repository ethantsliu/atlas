import { useEffect } from "react";
import type { Camera3d } from "../lib/camera";
import { fly3d } from "../lib/flight";

type FlyGraph = Camera3d & {
  renderer: () => { domElement: HTMLCanvasElement };
};
type FlyRef = { current: FlyGraph | undefined };

export function wheelMove(delta: number, mode: number, height: number): number {
  if (!Number.isFinite(delta) || delta === 0) return 0;
  const unit = mode === 1 ? 16 : mode === 2 ? Math.max(height, 1) : 1;
  const pixels = Math.max(-240, Math.min(240, delta * unit));
  return -pixels / 600;
}

export function useFly(graphRef: FlyRef): void {
  useEffect(() => {
    let frame = 0;
    let canvas: HTMLCanvasElement | null = null;
    const fly = (event: WheelEvent) => {
      if (event.ctrlKey) return;
      const ratio = wheelMove(event.deltaY, event.deltaMode, canvas?.clientHeight ?? 0);
      const graph = graphRef.current;
      if (!graph || ratio === 0) return;
      if (!fly3d(graph, ratio)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    const bind = () => {
      canvas = graphRef.current?.renderer().domElement ?? null;
      if (!canvas) {
        if (typeof requestAnimationFrame === "function") {
          frame = requestAnimationFrame(bind);
        }
        return;
      }
      canvas.addEventListener("wheel", fly, { capture: true, passive: false });
    };
    bind();
    return () => {
      if (frame) cancelAnimationFrame(frame);
      canvas?.removeEventListener("wheel", fly, true);
    };
  }, [graphRef]);
}
