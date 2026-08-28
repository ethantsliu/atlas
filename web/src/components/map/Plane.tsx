import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import {
  OrthographicCamera,
  Points,
  Scene,
  WebGLRenderer,
  type WebGLRendererParameters,
} from "three";
import { usePoints, type PointApi } from "../../hooks/points";
import type { Theme } from "../../hooks/theme";
import type { CloudData, CloudPick } from "../../lib/cloud";
import type { PickOrder } from "../../lib/order";
import { moveCloud, type CloudSwarm } from "../../lib/swarm";
import "../../plane.css";
import "./status.css";

export type PlaneView = { k: number; x: number; y: number };

export type PlaneRef = {
  block: () => void;
  drop: () => void;
  take: () => boolean;
  view: (view: PlaneView) => void;
};

type PlaneProps = {
  active: boolean;
  canvas: HTMLCanvasElement | null;
  data: CloudData | null;
  height: number;
  onPick: (pick: CloudPick) => void;
  onReady: (ready: boolean) => void;
  order: PickOrder;
  theme: Theme;
  width: number;
};

type PlaneHost = {
  camera: () => OrthographicCamera;
  renderer: () => WebGLRenderer;
  scene: () => Scene;
};

export type PlaneStatus = "ready" | "lost" | "retrying" | "unsupported";

export function watchPlane(
  canvas: HTMLCanvasElement,
  lost: () => void,
  restored: () => void,
): () => void {
  const onLoss = (event: Event) => {
    event.preventDefault();
    lost();
  };
  canvas.addEventListener("webglcontextlost", onLoss);
  canvas.addEventListener("webglcontextrestored", restored);
  return () => {
    canvas.removeEventListener("webglcontextlost", onLoss);
    canvas.removeEventListener("webglcontextrestored", restored);
  };
}

export function planeRatio(count: number, ratio: number): number {
  if (count >= 100_000) return 1;
  return Math.min(Number.isFinite(ratio) && ratio > 0 ? ratio : 1, 1.5);
}

export function planeDepth(
  data: CloudData,
  view: PlaneView,
  event: PointerEvent | MouseEvent,
  canvas: HTMLCanvasElement,
  index: number,
): number {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (
    rect.width <= 0 ||
    rect.height <= 0 ||
    view.k <= 0 ||
    index < 0 ||
    index >= data.loaded
  ) {
    return Number.POSITIVE_INFINITY;
  }
  const offset = index * 3;
  const dx = data.positions[offset] * view.k + view.x - x;
  const dy = data.positions[offset + 1] * view.k + view.y - y;
  return Math.hypot(dx, dy);
}

function makeHost(canvas: HTMLCanvasElement): PlaneHost | null {
  const context = canvas.getContext("webgl2", {
    alpha: true,
    antialias: false,
    depth: true,
    powerPreference: "high-performance",
  });
  if (!context) return null;
  const renderer = new WebGLRenderer({
    alpha: true,
    antialias: false,
    canvas,
    context,
  } as WebGLRendererParameters);
  renderer.setClearColor(0x000000, 0);
  const scene = new Scene();
  const camera = new OrthographicCamera(-1, 1, -1, 1, 0.01, 10_000);
  camera.position.set(0, 0, 1_000);
  camera.lookAt(0, 0, 0);
  return {
    camera: () => camera,
    renderer: () => renderer,
    scene: () => scene,
  };
}

function showPlane(
  host: PlaneHost,
  view: PlaneView,
  width: number,
  height: number,
  radius: number,
) {
  if (width <= 0 || height <= 0 || view.k <= 0) return;
  const camera = host.camera();
  const depth = Math.max(1, radius);
  camera.left = -view.x / view.k;
  camera.right = (width - view.x) / view.k;
  camera.top = -view.y / view.k;
  camera.bottom = (height - view.y) / view.k;
  camera.near = 0.01;
  camera.far = depth * 4 + 10;
  camera.position.set(0, 0, depth * 2 + 1);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  host.renderer().render(host.scene(), camera);
}

export function movePlane(points: CloudSwarm | undefined, draw: () => void): void {
  if (points) moveCloud(points, draw);
  draw();
}

function PlaneNotice({ status, retry }: { status: PlaneStatus; retry: () => void }) {
  if (status === "ready") return null;
  const message =
    status === "lost"
      ? "Paper map paused; the core map remains available."
      : status === "unsupported"
        ? "Paper map unavailable; the core map remains available."
        : "Restoring the paper map…";
  return (
    <aside className="graph-status" role="status" aria-live="polite">
      <span>{message}</span>
      <button type="button" onClick={retry} disabled={status === "retrying"}>
        {status === "retrying" ? "Restoring…" : "Retry paper map"}
      </button>
    </aside>
  );
}

export const CloudPlane = forwardRef<PlaneRef, PlaneProps>(function CloudPlane(
  { active, canvas, data, height, onPick, onReady, order, theme, width },
  ref,
) {
  const ownRef = useRef<HTMLCanvasElement>(null);
  const pointRef = useRef<PointApi>();
  const viewRef = useRef<PlaneView>({ k: 1, x: width / 2, y: height / 2 });
  const [epoch, setEpoch] = useState(0);
  const [host, setHost] = useState<PlaneHost | null>(null);
  const [status, setStatus] = useState<PlaneStatus>("retrying");
  const retry = useCallback(() => {
    pointRef.current = undefined;
    setHost(null);
    onReady(false);
    setStatus("retrying");
    setEpoch((value) => value + 1);
  }, [onReady]);

  useEffect(() => {
    const element = ownRef.current;
    if (!element) return;
    let next: PlaneHost | null = null;
    try {
      next = makeHost(element);
    } catch {
      next = null;
    }
    if (!next) {
      onReady(false);
      setStatus("unsupported");
      return;
    }
    const stopWatch = watchPlane(
      element,
      () => {
        pointRef.current = undefined;
        setHost(null);
        onReady(false);
        setStatus("lost");
      },
      retry,
    );
    pointRef.current = next;
    setHost(next);
    setStatus("ready");
    onReady(true);
    return () => {
      stopWatch();
      pointRef.current = undefined;
      onReady(false);
      queueMicrotask(() => {
        next.renderer().dispose();
        next.renderer().forceContextLoss();
      });
    };
  }, [epoch, onReady, retry]);

  const hit = usePoints({
    active,
    canvas,
    data: host && canvas ? data : null,
    depth:
      data && canvas
        ? (index, event, target) =>
            planeDepth(data, viewRef.current, event, target, index)
        : undefined,
    graphRef: pointRef,
    onPick,
    order,
    theme,
  });

  useImperativeHandle(
    ref,
    () => ({
      block: hit.block,
      drop: hit.drop,
      take: hit.take,
      view: (view) => {
        viewRef.current = view;
        if (host) {
          const draw = () =>
            showPlane(host, viewRef.current, width, height, data?.radius ?? 1);
          const points = host.scene().getObjectByName("archive-cloud") as
            CloudSwarm | undefined;
          movePlane(points, draw);
        }
      },
    }),
    [data?.radius, height, hit.block, hit.drop, hit.take, host, width],
  );

  useEffect(() => {
    if (!host) return;
    const ratio = planeRatio(data?.loaded ?? 0, window.devicePixelRatio);
    host.renderer().setPixelRatio(ratio);
    host.renderer().setSize(width, height, false);
    let frame = 0;
    let quiet = 0;
    let prior = -1;
    const draw = () => {
      showPlane(host, viewRef.current, width, height, data?.radius ?? 1);
      const points = host.scene().getObjectByName("archive-cloud") as
        Points | undefined;
      const count = points?.geometry.drawRange.count ?? 0;
      quiet = count === prior ? quiet + 1 : 0;
      prior = count;
      if (data && (count < data.loaded || quiet < 2)) {
        frame = requestAnimationFrame(draw);
      }
    };
    draw();
    return () => cancelAnimationFrame(frame);
  }, [active, data, data?.loaded, data?.radius, height, host, theme, width]);

  return (
    <>
      <canvas
        className="cloud-plane"
        data-engine={status}
        key={epoch}
        ref={ownRef}
        aria-hidden="true"
      />
      <PlaneNotice status={status} retry={retry} />
      {hit.tip && (
        <div
          className="swarm-tip cloud-tip"
          data-depth={hit.tip.depth}
          role="tooltip"
          style={{ left: hit.tip.x + 14, top: hit.tip.y + 14 }}
        >
          {hit.tip.label}
        </div>
      )}
    </>
  );
});
