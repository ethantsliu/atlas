import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export type RenderMode = "3d" | "2d";
export type WebglStatus = "ready" | "unsupported" | "lost" | "retrying";

export type WebglState = {
  mode: RenderMode;
  status: WebglStatus;
  retry: () => void;
};

type ContextHandlers = {
  lost: () => void;
  restored: () => void;
};

type CanvasMaker = () => HTMLCanvasElement;

function makeCanvas(): HTMLCanvasElement {
  return document.createElement("canvas");
}

export function probeWebgl(create: CanvasMaker = makeCanvas): boolean {
  try {
    const context = create().getContext("webgl2");
    if (!context) return false;
    context.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

export function watchCanvas(
  canvas: HTMLCanvasElement,
  handlers: ContextHandlers,
): () => void {
  const onLoss = (event: Event) => {
    event.preventDefault();
    handlers.lost();
  };
  const onRestore = () => handlers.restored();
  canvas.addEventListener("webglcontextlost", onLoss);
  canvas.addEventListener("webglcontextrestored", onRestore);
  return () => {
    canvas.removeEventListener("webglcontextlost", onLoss);
    canvas.removeEventListener("webglcontextrestored", onRestore);
  };
}

function watchRoot(root: HTMLElement, handlers: ContextHandlers): () => void {
  const watched = new Map<HTMLCanvasElement, () => void>();
  const sync = () => {
    const present = new Set(root.querySelectorAll("canvas"));
    for (const [canvas, cleanup] of watched) {
      if (present.has(canvas)) continue;
      cleanup();
      watched.delete(canvas);
    }
    for (const canvas of present) {
      if (!watched.has(canvas)) watched.set(canvas, watchCanvas(canvas, handlers));
    }
  };
  sync();
  const observer = new MutationObserver(sync);
  observer.observe(root, { childList: true, subtree: true });
  return () => {
    observer.disconnect();
    watched.forEach((cleanup) => cleanup());
    watched.clear();
  };
}

export function useWebgl(
  root: RefObject<HTMLElement>,
  requested: RenderMode,
): WebglState {
  const [supported, setSupported] = useState<boolean | null>(() =>
    requested === "3d" ? probeWebgl() : null,
  );
  const [status, setStatus] = useState<WebglStatus>(
    supported === false ? "unsupported" : "ready",
  );
  const mode =
    requested === "3d" && supported === true && status === "ready" ? "3d" : "2d";
  const timerRef = useRef<number>();
  const lost = useCallback(() => {
    setSupported(false);
    setStatus("lost");
  }, []);
  const restored = useCallback(() => {
    setSupported(false);
    setStatus("lost");
  }, []);

  useEffect(() => {
    if (mode !== "3d" || !root.current) return;
    return watchRoot(root.current, { lost, restored });
  }, [lost, mode, restored, root]);

  useEffect(() => {
    if (requested !== "3d" || supported !== null) return;
    const ready = probeWebgl();
    setSupported(ready);
    setStatus(ready ? "ready" : "unsupported");
  }, [requested, supported]);

  useEffect(
    () => () => {
      window.clearTimeout(timerRef.current);
    },
    [],
  );

  const retry = useCallback(() => {
    window.clearTimeout(timerRef.current);
    setStatus("retrying");
    timerRef.current = window.setTimeout(() => {
      const ready = probeWebgl();
      setSupported(ready);
      setStatus(ready ? "ready" : "unsupported");
    });
  }, []);

  return { mode, status, retry };
}
