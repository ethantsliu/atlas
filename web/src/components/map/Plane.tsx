import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  OrthographicCamera,
  Points,
  Scene,
  WebGLRenderer,
  type WebGLRendererParameters,
} from "three";
import { pickSize, usePoints, type PointApi, type PointHit } from "../../hooks/points";
import type { Theme } from "../../hooks/theme";
import type { CloudData, CloudPick } from "../../lib/cloud";
import type { PickOrder } from "../../lib/order";
import "../../plane.css";

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

export function planeHit(
  data: CloudData,
  view: PlaneView,
  event: PointerEvent | MouseEvent,
  canvas: HTMLCanvasElement,
): PointHit {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (rect.width <= 0 || rect.height <= 0 || view.k <= 0) {
    return { distance: Number.POSITIVE_INFINITY, index: null, x, y };
  }
  const pointer = "pointerType" in event ? event.pointerType : undefined;
  let nearest = (pickSize(pointer) / 2) ** 2;
  let picked: number | null = null;
  for (let index = 0; index < data.loaded; index += 1) {
    const offset = index * 3;
    const dx = data.positions[offset] * view.k + view.x - x;
    const dy = data.positions[offset + 1] * view.k + view.y - y;
    const distance = dx * dx + dy * dy;
    if (distance > nearest) continue;
    nearest = distance;
    picked = index;
  }
  return {
    distance: picked == null ? Number.POSITIVE_INFINITY : Math.sqrt(nearest),
    index: picked,
    x,
    y,
  };
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

export const CloudPlane = forwardRef<PlaneRef, PlaneProps>(function CloudPlane(
  { active, canvas, data, height, onPick, onReady, order, theme, width },
  ref,
) {
  const ownRef = useRef<HTMLCanvasElement>(null);
  const pointRef = useRef<PointApi>();
  const viewRef = useRef<PlaneView>({ k: 1, x: width / 2, y: height / 2 });
  const [host, setHost] = useState<PlaneHost | null>(null);

  useEffect(() => {
    const element = ownRef.current;
    if (!element) return;
    const next = makeHost(element);
    if (!next) {
      onReady(false);
      return;
    }
    pointRef.current = next;
    setHost(next);
    onReady(true);
    return () => {
      pointRef.current = undefined;
      onReady(false);
      queueMicrotask(() => {
        next.renderer().dispose();
        next.renderer().forceContextLoss();
      });
    };
  }, [onReady]);

  const hit = usePoints({
    active,
    canvas,
    data: host && canvas ? data : null,
    graphRef: pointRef,
    hit:
      data && canvas
        ? (event, target) => planeHit(data, viewRef.current, event, target)
        : undefined,
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
        if (host) showPlane(host, view, width, height, data?.radius ?? 1);
      },
    }),
    [data?.radius, height, hit.block, hit.drop, hit.take, host, width],
  );

  useEffect(() => {
    if (!host) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
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
      <canvas className="cloud-plane" ref={ownRef} aria-hidden="true" />
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
