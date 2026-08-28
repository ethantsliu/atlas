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
import type { Theme } from "./theme";
import { bindChange } from "./control";
import type { PickOrder } from "../lib/order";
const HOVER_WAIT = 120;
const DENSE_HOVER_WAIT = 700;
const META_LIMIT = 4;
export const CLOUD_HOVER_LIMIT = 100_000;
export type PointTip = { depth: number; label: string; x: number; y: number };

type PointInput = {
  graphRef: PointRef;
  canvas?: HTMLCanvasElement | null;
  hit?: (event: PointerEvent | MouseEvent, canvas: HTMLCanvasElement) => PointHit;
  data: CloudData | null;
  active: boolean;
  theme: Theme;
  onPick: (pick: CloudPick) => void;
  order: PickOrder;
};
export type PointHit = {
  distance: number;
  index: number | null;
  x: number;
  y: number;
};

export type PointApi = Pick<GraphApi, "camera" | "renderer" | "scene"> & {
  controls?: GraphApi["controls"];
};

export type PointRef = { current: PointApi | undefined };
type Claim = {
  committed: boolean;
  distance: number;
  index: number;
  paper?: CloudPick;
  pending: boolean;
  x: number;
  y: number;
};
type Hover = {
  distance: number;
  index: number;
  paper?: CloudPick;
  x: number;
  y: number;
};
type Down = { x: number; y: number };
type Ref<T> = { current: T };
type PointRefs = {
  block: Ref<number>;
  claim: Ref<Claim | null>;
  hover: Ref<Hover | null>;
  hidden: Ref<boolean>;
  pick: Ref<(paper: CloudPick, depth: number) => void>;
  points: Ref<CloudSwarm | null>;
  request: Ref<number>;
  select: Ref<number>;
  target: Ref<Hover | null>;
};

function isHidden(refs: Pick<PointRefs, "hidden">) {
  return refs.hidden.current;
}

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

function gpuHit(
  canvas: HTMLCanvasElement,
  graph: PointApi,
  picker: ReturnType<typeof makeGpuPick>,
  event: PointerEvent | MouseEvent,
) {
  const rect = canvas.getBoundingClientRect();
  const camera = graph.camera() as Camera;
  const match = picker.pick(
    camera,
    event.clientX,
    event.clientY,
    rect,
    pickSize("pointerType" in event ? event.pointerType : undefined),
  );
  return {
    distance: match?.distance ?? Number.POSITIVE_INFINITY,
    index: match?.index ?? null,
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

export function pickBound(
  refs: Pick<PointRefs, "claim" | "pick" | "target">,
  event: MouseEvent | PointerEvent,
) {
  const claim = refs.claim.current;
  const target = refs.target.current;
  const nearby =
    target && Math.hypot(event.clientX - target.x, event.clientY - target.y) <= 10;
  const paper =
    claim?.paper ??
    (claim && nearby && target.index === claim.index ? target.paper : undefined);
  if (
    !claim ||
    claim.committed ||
    ("isPrimary" in event && !event.isPrimary) ||
    event.button !== 0 ||
    !paper ||
    Math.hypot(event.clientX - claim.x, event.clientY - claim.y) > 5
  ) {
    return;
  }
  claim.committed = true;
  claim.paper = paper;
  refs.pick.current(paper, claim.distance);
}

export function clearHover(
  refs: Pick<PointRefs, "hover" | "request" | "target">,
  setTip: (tip: PointTip | null) => void,
) {
  refs.hover.current = null;
  refs.target.current = null;
  refs.request.current += 1;
  setTip(null);
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

function hoverAt(
  match: { distance: number; index: number },
  event: PointerEvent,
): Hover {
  return { ...match, x: event.clientX, y: event.clientY };
}

function queueClaim(
  input: PointInput,
  refs: PointRefs,
  setTip: (tip: PointTip | null) => void,
  load: (index: number) => Promise<CloudPick | null>,
  claim: Claim,
  at: { x: number; y: number },
) {
  input.order.claim(1, claim.distance, () => {
    const token = ++refs.select.current;
    claim.committed = true;
    setTip({ depth: claim.distance, label: "Loading Paper…", ...at });
    void load(claim.index)
      .then((paper) => {
        if (
          !paper ||
          token !== refs.select.current ||
          refs.claim.current !== claim ||
          performance.now() < refs.block.current
        ) {
          return;
        }
        claim.paper = paper;
        claim.pending = false;
        setTip({
          depth: claim.distance,
          label: `Paper · ${paper.paper.title}`,
          ...at,
        });
        refs.pick.current(paper, claim.distance);
      })
      .catch(() => {
        if (token !== refs.select.current) return;
        setTip({
          depth: claim.distance,
          label: "Paper details unavailable · select to retry",
          ...at,
        });
      });
  });
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
  const points = buildCloud(data, input.theme, renderer);
  growCloud(points, data);
  points.visible = input.active;
  refs.points.current = points;
  graph.scene().add(points);
  const canvas = input.canvas ?? renderer.domElement;
  const picker = input.hit ? null : makeGpuPick(renderer, points, data.positions);
  const controller = new AbortController();
  const cache = new Map<string, Promise<CloudPaper[]>>();
  const hit = (event: PointerEvent | MouseEvent) =>
    input.hit?.(event, canvas) ?? gpuHit(canvas, graph, picker!, event);
  const load = (index: number) => loadPaper(data, cache, controller.signal, index);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let moved: PointerEvent | null = null;
  let down: Down | null = null;
  let pressed = false;
  const show = (event: PointerEvent) => {
    if (isHidden(refs) || performance.now() < refs.block.current) {
      setProbing(false);
      return;
    }
    const match = hit(event);
    setProbing(false);
    const token = ++refs.request.current;
    if (match.index == null) {
      clearHover(refs, setTip);
      return;
    }
    const index = match.index;
    refs.hover.current = hoverAt({ distance: match.distance, index }, event);
    setTip({ depth: match.distance, label: "Loading Paper…", x: match.x, y: match.y });
    void load(index)
      .then((paper) => {
        if (!paper || token !== refs.request.current) return;
        if (refs.hover.current?.index === index) refs.hover.current.paper = paper;
        refs.target.current = {
          ...hoverAt({ distance: match.distance, index }, event),
          paper,
        };
        setTip({
          depth: match.distance,
          label: `Paper · ${paper.paper.title}`,
          x: match.x,
          y: match.y,
        });
      })
      .catch(() => {
        if (token === refs.request.current) {
          setTip({
            depth: match.distance,
            label: "Paper details unavailable · hover to retry",
            x: match.x,
            y: match.y,
          });
        }
      });
  };
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
    setProbing(data.loaded > CLOUD_HOVER_LIMIT);
    const prior = refs.target.current ?? refs.hover.current;
    if (hoverMoved(prior, event)) {
      clearHover(refs, setTip);
    }
    moved = event;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      if (moved) show(moved);
    }, hoverWait(data.loaded));
  };
  const leave = () => {
    down = null;
    pressed = false;
    clear();
  };
  const change = () => {
    down = null;
    clear();
  };
  const press = (event: PointerEvent) => {
    input.order.begin(event.timeStamp);
    refs.claim.current = null;
    refs.select.current += 1;
    stop();
    if (isHidden(refs) || !event.isPrimary || event.button !== 0) {
      down = null;
      pressed = false;
      return;
    }
    down = { x: event.clientX, y: event.clientY };
    pressed = true;
  };
  const release = (event: MouseEvent | PointerEvent) => {
    const start = down;
    down = null;
    pressed = false;
    if (!validRelease(start, event, refs)) return;
    const hovered = refs.target.current ?? refs.hover.current;
    const match = hit(event);
    if (match.index == null) return;
    refs.claim.current = {
      committed: false,
      distance: match.distance,
      index: match.index,
      paper: hovered?.index === match.index ? hovered.paper : undefined,
      pending: true,
      ...start,
    };
    pickBound(refs, event);
  };
  const choose = (event: MouseEvent) => {
    const claim = refs.claim.current;
    if (timer) clearTimeout(timer);
    timer = undefined;
    moved = null;
    if (
      isHidden(refs) ||
      (performance.now() < refs.block.current && !claim?.paper) ||
      !claim ||
      Math.hypot(event.clientX - claim.x, event.clientY - claim.y) > 5
    ) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const at = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    if (claim.paper) {
      if (!claim.committed) {
        claim.committed = true;
        refs.pick.current(claim.paper, claim.distance);
      }
      window.setTimeout(() => {
        if (refs.claim.current === claim) claim.pending = false;
      }, 0);
      return;
    }
    queueClaim(input, refs, setTip, load, claim, at);
  };
  const dropChange = bindChange(graph.controls?.(), change);
  const dropEvents = bindPoints(canvas, { choose, leave, move, press, release });
  return () => {
    if (timer) clearTimeout(timer);
    controller.abort();
    dropEvents();
    dropChange();
    picker?.dispose();
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
