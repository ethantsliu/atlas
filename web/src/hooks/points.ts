import { useCallback, useEffect, useRef, useState } from "react";
import { type Camera } from "three";
import type { GraphApi } from "../components/map/Driver";
import {
  cloudPaper,
  cloudRange,
  fetchCloudMeta,
  type CloudData,
  type CloudPaper,
  type CloudPick,
} from "../lib/cloud";
import {
  buildCloud,
  dropCloud,
  growCloud,
  paintCloud,
  type CloudSwarm,
} from "../lib/swarm";
import type { GraphNode } from "../types";
import { makeGpuPick } from "./gpu";
import {
  choosePoint,
  clearHover,
  isHidden,
  showPoint,
  type Claim,
  type Hover,
  type PointRefs,
  type PointTip,
} from "./probe";
import type { Theme } from "./theme";
import { bindChange } from "./control";
import type { PickOrder } from "../lib/order";
const HOVER_WAIT = 120;
const DENSE_HOVER_WAIT = 700;
const META_LIMIT = 2;
export const CLOUD_HOVER_LIMIT = 100_000;
export { clearHover, pickBound, reuseHit, type PointTip } from "./probe";

type PointInput = {
  graphRef: PointRef;
  canvas?: HTMLCanvasElement | null;
  depth?: (
    index: number,
    event: PointerEvent | MouseEvent,
    canvas: HTMLCanvasElement,
  ) => number;
  data: CloudData | null;
  active: boolean;
  theme: Theme;
  onPick: (pick: CloudPick) => void;
  order: PickOrder;
};
export type PointApi = Pick<GraphApi, "camera" | "renderer" | "scene"> & {
  controls?: GraphApi["controls"];
};

export type PointRef = { current: PointApi | undefined };
type Down = { pointer?: string; x: number; y: number };

function dropPoints(
  graph: PointApi,
  points: CloudSwarm,
  refs: PointRefs,
  setTip: (tip: PointTip | null) => void,
) {
  graph.scene().remove(points);
  dropCloud(points);
  points.geometry.dispose();
  const materials = Array.isArray(points.material)
    ? points.material
    : [points.material];
  materials.forEach((material) => material.dispose());
  refs.claim.current = null;
  refs.hover.current = null;
  refs.target.current = null;
  refs.points.current = null;
  refs.request.current += 1;
  refs.select.current += 1;
  setTip(null);
}

async function gpuHit(
  canvas: HTMLCanvasElement,
  graph: PointApi,
  picker: ReturnType<typeof makeGpuPick>,
  event: PointerEvent | MouseEvent,
  depth?: PointInput["depth"],
  pointer?: string,
) {
  const rect = canvas.getBoundingClientRect();
  const camera = graph.camera() as Camera;
  const match = await picker.pick(
    camera,
    event.clientX,
    event.clientY,
    rect,
    pickSize(pointer ?? ("pointerType" in event ? event.pointerType : undefined)),
  );
  return {
    distance:
      match == null
        ? Number.POSITIVE_INFINITY
        : (depth?.(match.index, event, canvas) ?? match.distance),
    index: match?.index ?? null,
    valid: match?.valid,
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

export function pickSize(pointer?: string): number {
  return pointer === "touch" ? 24 : 8;
}

export function hoverWait(count: number): number {
  return count <= CLOUD_HOVER_LIMIT ? HOVER_WAIT : DENSE_HOVER_WAIT;
}

export function hoverMoved(
  hover: Pick<Hover, "x" | "y"> | null,
  event: Pick<PointerEvent, "clientX" | "clientY">,
): boolean {
  return Boolean(hover && (event.clientX !== hover.x || event.clientY !== hover.y));
}

export function cacheMeta<T>(
  cache: Map<string, Promise<T>>,
  path: string,
  load: () => Promise<T>,
): Promise<T> {
  const cached = cache.get(path);
  if (cached) {
    cache.delete(path);
    cache.set(path, cached);
    return cached;
  }
  const request = load();
  cache.set(path, request);
  while (cache.size > META_LIMIT) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
  void request.catch(() => {
    if (cache.get(path) === request) cache.delete(path);
  });
  return request;
}

async function loadPaper(
  data: CloudData,
  cache: Map<string, Promise<CloudPaper[]>>,
  signal: AbortSignal,
  index: number,
) {
  const range = cloudRange(data, index);
  if (!range) return null;
  const request = cacheMeta(cache, range.meta.path, () =>
    fetchCloudMeta(
      range,
      signal,
      data.scopes.subarray(range.start, range.start + range.count),
    ),
  );
  const paper = cloudPaper(await request, range, index);
  return paper ? { index, paper } : null;
}

export function cloudFront(
  graph: PointRef["current"],
  node: GraphNode,
  distance: number,
): boolean {
  return distance <= nodeDepth(graph, node);
}

export function nodeDepth(
  graph: Pick<GraphApi, "camera"> | undefined,
  node: GraphNode,
): number {
  if (!graph) return Number.POSITIVE_INFINITY;
  const paper = node.kind === "paper";
  const x = paper ? (node.sx ?? node.x) : node.x;
  const y = paper ? (node.sy ?? node.y) : node.y;
  const z = paper ? (node.sz ?? node.z) : node.z;
  if (![x, y, z].every(Number.isFinite)) return Number.POSITIVE_INFINITY;
  const camera = graph.camera() as Camera;
  const depth = Math.hypot(
    camera.position.x - x!,
    camera.position.y - y!,
    camera.position.z - z!,
  );
  return depth;
}

type PointEvents = {
  choose: (event: MouseEvent) => void;
  leave: () => void;
  move: (event: PointerEvent) => void;
  press: (event: PointerEvent) => void;
  release: (event: MouseEvent | PointerEvent) => void;
};

function bindPoints(canvas: HTMLCanvasElement, events: PointEvents) {
  canvas.addEventListener("pointermove", events.move);
  canvas.addEventListener("pointerleave", events.leave);
  canvas.addEventListener("pointerdown", events.press);
  window.addEventListener("pointerup", events.release, true);
  window.addEventListener("mouseup", events.release, true);
  canvas.addEventListener("click", events.choose, true);
  return () => {
    canvas.removeEventListener("pointermove", events.move);
    canvas.removeEventListener("pointerleave", events.leave);
    canvas.removeEventListener("pointerdown", events.press);
    window.removeEventListener("pointerup", events.release, true);
    window.removeEventListener("mouseup", events.release, true);
    canvas.removeEventListener("click", events.choose, true);
  };
}

function validRelease(
  start: Down | null,
  event: MouseEvent | PointerEvent,
  refs: Pick<PointRefs, "hidden">,
): start is Down {
  return Boolean(
    start &&
    !isHidden(refs) &&
    (!("isPrimary" in event) || event.isPrimary) &&
    event.button === 0 &&
    Math.hypot(event.clientX - start.x, event.clientY - start.y) <= 5,
  );
}

function mountPoints(
  input: PointInput,
  refs: PointRefs,
  setTip: (tip: PointTip | null) => void,
  setProbing: (value: boolean) => void,
) {
  const graph = input.graphRef.current;
  const data = input.data;
  if (!graph || !data || data.scopes.length === 0) return;
  const renderer = graph.renderer();
  const redraw = input.canvas
    ? undefined
    : () => {
        if (input.graphRef.current !== graph) return;
        renderer.render(graph.scene(), graph.camera() as Camera);
      };
  const points = buildCloud(data, input.theme, renderer, redraw);
  growCloud(points, data);
  points.visible = input.active;
  refs.points.current = points;
  graph.scene().add(points);
  const canvas = input.canvas ?? renderer.domElement;
  const picker = makeGpuPick(renderer, points, data.positions);
  const controller = new AbortController();
  const cache = new Map<string, Promise<CloudPaper[]>>();
  const hit = (event: PointerEvent | MouseEvent, pointer?: string) =>
    gpuHit(canvas, graph, picker, event, input.depth, pointer);
  const load = (index: number) => loadPaper(data, cache, controller.signal, index);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let moved: PointerEvent | null = null;
  let down: Down | null = null;
  let released: Down | null = null;
  let pressed = false;
  const show = (event: PointerEvent) =>
    showPoint({ event, hit, load, refs, setProbing, setTip });
  const stop = () => {
    if (timer) clearTimeout(timer);
    timer = undefined;
    moved = null;
    setProbing(false);
    setTip(null);
  };
  const clear = () => {
    stop();
    clearHover(refs, setTip);
  };
  const move = (event: PointerEvent) => {
    if (pressed) {
      if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) {
        down = null;
      }
      clear();
      return;
    }
    if (isHidden(refs)) {
      clear();
      return;
    }
    refs.request.current += 1;
    setProbing(data.loaded > CLOUD_HOVER_LIMIT);
    const prior = refs.target.current ?? refs.hover.current;
    if (hoverMoved(prior, event)) {
      clearHover(refs, setTip);
    }
    moved = event;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      if (moved) void show(moved);
    }, hoverWait(data.loaded));
  };
  const leave = () => {
    down = null;
    pressed = false;
    clear();
  };
  const change = () => {
    refs.claim.current = null;
    refs.select.current += 1;
    clear();
  };
  const press = (event: PointerEvent) => {
    input.order.begin(event.timeStamp);
    refs.claim.current = null;
    refs.request.current += 1;
    refs.select.current += 1;
    released = null;
    stop();
    if (isHidden(refs) || !event.isPrimary || event.button !== 0) {
      down = null;
      pressed = false;
      return;
    }
    down = {
      pointer: event.pointerType,
      x: event.clientX,
      y: event.clientY,
    };
    pressed = true;
  };
  const release = (event: MouseEvent | PointerEvent) => {
    const start = down;
    down = null;
    pressed = false;
    if (!validRelease(start, event, refs)) return;
    released = start;
  };
  const choose = (event: MouseEvent) => {
    const start = released;
    released = null;
    if (timer) clearTimeout(timer);
    timer = undefined;
    moved = null;
    if (
      isHidden(refs) ||
      !start ||
      Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5
    ) {
      return;
    }
    choosePoint({
      canvas,
      event,
      hit,
      load,
      order: input.order,
      pointer: start.pointer,
      refs,
      setTip,
      start,
      token: refs.select.current,
    });
  };
  const dropChange = bindChange(graph.controls?.(), change);
  const dropEvents = bindPoints(canvas, { choose, leave, move, press, release });
  return () => {
    if (timer) clearTimeout(timer);
    controller.abort();
    dropEvents();
    dropChange();
    picker.dispose();
    dropPoints(graph, points, refs, setTip);
  };
}

export function usePoints(input: PointInput): {
  tip: PointTip | null;
  probing: boolean;
  block: () => void;
  drop: () => void;
  take: (node?: GraphNode) => boolean;
} {
  const [tip, setTip] = useState<PointTip | null>(null);
  const [probing, setProbing] = useState(false);
  const pickRef = useRef<(paper: CloudPick, depth: number) => void>(() => {});
  const blockRef = useRef(0);
  const claimRef = useRef<Claim | null>(null);
  const hoverRef = useRef<Hover | null>(null);
  const hiddenRef = useRef(!input.active);
  const pointsRef = useRef<CloudSwarm | null>(null);
  const requestRef = useRef(0);
  const selectRef = useRef(0);
  const targetRef = useRef<Hover | null>(null);
  pickRef.current = (paper, depth) => {
    input.order.claim(1, depth, () => input.onPick(paper));
  };
  const block = useCallback(() => {
    blockRef.current = performance.now() + 180;
    hoverRef.current = null;
    targetRef.current = null;
    requestRef.current += 1;
    selectRef.current += 1;
    setProbing(false);
    setTip(null);
  }, []);
  const drop = useCallback(() => {
    claimRef.current = null;
  }, []);
  const take = useCallback(
    (node?: GraphNode) => {
      const claim = claimRef.current;
      if (!claim?.pending || !node) return Boolean(claim?.pending);
      return cloudFront(input.graphRef.current, node, claim.distance);
    },
    [input.graphRef],
  );
  useEffect(() => {
    hiddenRef.current = !input.active;
    if (pointsRef.current) pointsRef.current.visible = input.active;
    if (input.active) return;
    claimRef.current = null;
    hoverRef.current = null;
    targetRef.current = null;
    requestRef.current += 1;
    selectRef.current += 1;
    setProbing(false);
    setTip(null);
  }, [input.active]);
  useEffect(
    () =>
      mountPoints(
        input,
        {
          block: blockRef,
          claim: claimRef,
          hover: hoverRef,
          hidden: hiddenRef,
          pick: pickRef,
          points: pointsRef,
          request: requestRef,
          select: selectRef,
          target: targetRef,
        },
        setTip,
        setProbing,
      ),
    [input.canvas, input.data, input.graphRef],
  );
  useEffect(() => {
    if (pointsRef.current && input.data) growCloud(pointsRef.current, input.data);
  }, [input.data?.loaded]);
  useEffect(() => {
    if (pointsRef.current) paintCloud(pointsRef.current, input.theme);
  }, [input.theme]);
  return { tip, probing, block, drop, take };
}
