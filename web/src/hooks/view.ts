import { useCallback, useEffect, useRef } from "react";
import {
  formatCamera,
  read3d,
  show3d,
  type Camera3d,
  type CameraView,
} from "../lib/camera";

type ViewGraph = Camera3d & {
  renderer: () => { domElement: HTMLCanvasElement };
};
type ViewRef = { current: ViewGraph | undefined };
type Pending = { key: string; view: CameraView };

export function useView(graphRef: ViewRef, view: CameraView | null, ready: boolean) {
  const pendingRef = useRef<Pending | null>(null);
  const restoredRef = useRef<string | null>(null);
  const canceledRef = useRef<string | null>(null);
  const keyRef = useRef<string | null>(null);

  const showView = useCallback(() => {
    const pending = pendingRef.current;
    const graph = graphRef.current;
    if (!pending || !graph || !show3d(graph, pending.view)) return;
    if (formatCamera(read3d(graph)) !== pending.key) return;
    restoredRef.current = pending.key;
    pendingRef.current = null;
  }, [graphRef]);

  useEffect(() => {
    const key = formatCamera(view);
    if (keyRef.current !== key) {
      keyRef.current = key;
      canceledRef.current = null;
    }
    if (!key) return;
    let frame = 0;
    let canvas: HTMLCanvasElement | null = null;
    const cancelView = () => {
      canceledRef.current = key;
      pendingRef.current = null;
    };
    const bindView = () => {
      canvas = graphRef.current?.renderer().domElement ?? null;
      if (!canvas) {
        if (typeof requestAnimationFrame === "function") {
          frame = requestAnimationFrame(bindView);
        }
        return;
      }
      canvas.addEventListener("pointerdown", cancelView, true);
      canvas.addEventListener("wheel", cancelView, true);
    };
    bindView();
    return () => {
      if (frame) cancelAnimationFrame(frame);
      canvas?.removeEventListener("pointerdown", cancelView, true);
      canvas?.removeEventListener("wheel", cancelView, true);
    };
  }, [graphRef, view]);

  useEffect(() => {
    const key = formatCamera(view);
    if (!view || !key) {
      pendingRef.current = null;
      restoredRef.current = null;
      return;
    }
    if (!ready || canceledRef.current === key) {
      pendingRef.current = null;
      return;
    }
    if (restoredRef.current === key) return;
    pendingRef.current = { key, view };
    if (typeof requestAnimationFrame !== "function") return;
    let frame = 0;
    const restoreFrame = () => {
      showView();
      if (pendingRef.current?.key === key) {
        frame = requestAnimationFrame(restoreFrame);
      }
    };
    frame = requestAnimationFrame(restoreFrame);
    return () => cancelAnimationFrame(frame);
  }, [ready, showView, view]);

  return showView;
}
