import { useCallback, useEffect, useRef, useState } from "react";
import { type Camera } from "three";
import type { GraphRef } from "../components/map/Driver";
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

const HOVER_LIMIT = 100_000;
const HOVER_WAIT = 120;
const META_LIMIT = 4;

export type PointTip = { label: string; x: number; y: number };

type PointInput = {
  graphRef: GraphRef;
  data: CloudData | null;
  active: boolean;
  theme: Theme;
  onPick: (pick: CloudPick) => void;
};
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
type Ref<T> = { current: T };
type PointRefs = {
  block: Ref<number>;
  claim: Ref<Claim | null>;
  hover: Ref<Hover | null>;
  mute: Ref<boolean>;
  hidden: Ref<boolean>;
  pick: Ref<(paper: CloudPick) => void>;
  points: Ref<CloudSwarm | null>;
  request: Ref<number>;
  select: Ref<number>;
  target: Ref<Hover | null>;
};

function isMuted(refs: Pick<PointRefs, "hidden" | "mute">) {
  return refs.hidden.current || refs.mute.current;
}

function dropPoints(
  graph: NonNullable<GraphRef["current"]>,
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
  graph: NonNullable<GraphRef["current"]>,
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
  refs.pick.current(paper);
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
  graph: GraphRef["current"],
  node: GraphNode,
  distance: number,
): boolean {
  if (!graph) return true;
  const paper = node.kind === "paper";
  const x = paper ? (node.sx ?? node.x) : node.x;
  const y = paper ? (node.sy ?? node.y) : node.y;
  const z = paper ? (node.sz ?? node.z) : node.z;
  if (![x, y, z].every(Number.isFinite)) return true;
  const camera = graph.camera() as Camera;
  const depth = Math.hypot(
    camera.position.x - x!,
    camera.position.y - y!,
    camera.position.z - z!,
  );
  return distance <= depth;
}

function hoverAt(
  match: { distance: number; index: number },
  event: PointerEvent,
): Hover {
  return { ...match, x: event.clientX, y: event.clientY };
}

function mountPoints(
  input: PointInput,
  refs: PointRefs,
  setTip: (tip: PointTip | null) => void,
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
  const canvas = renderer.domElement;
  const picker = makeGpuPick(renderer, points, data.positions);
  const controller = new AbortController();
  const cache = new Map<string, Promise<CloudPaper[]>>();
  const hit = (event: PointerEvent | MouseEvent) =>
    gpuHit(canvas, graph, picker, event);
  const load = (index: number) => loadPaper(data, cache, controller.signal, index);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let moved: PointerEvent | null = null;

  const show = (event: PointerEvent) => {
    if (isMuted(refs) || performance.now() < refs.block.current) {
      return;
    }
    const match = hit(event);
    const token = ++refs.request.current;
    if (match.index == null) {
      clearHover(refs, setTip);
      return;
    }
    const index = match.index;
    refs.hover.current = hoverAt({ distance: match.distance, index }, event);
    setTip({ label: "Loading Paper…", x: match.x, y: match.y });
    void load(index)
      .then((paper) => {
        if (!paper || token !== refs.request.current) return;
        if (refs.hover.current?.index === index) refs.hover.current.paper = paper;
        refs.target.current = {
          ...hoverAt({ distance: match.distance, index }, event),
          paper,
        };
        setTip({ label: `Paper · ${paper.paper.title}`, x: match.x, y: match.y });
      })
      .catch(() => {
        if (token === refs.request.current) {
          setTip({
            label: "Paper details unavailable · hover to retry",
            x: match.x,
            y: match.y,
          });
        }
      });
  };
  const move = (event: PointerEvent) => {
    if (isMuted(refs)) {
      if (timer) clearTimeout(timer);
      timer = undefined;
      moved = null;
      clearHover(refs, setTip);
      return;
    }
    const prior = refs.target.current ?? refs.hover.current;
    if (prior && Math.hypot(event.clientX - prior.x, event.clientY - prior.y) > 10) {
      clearHover(refs, setTip);
    }
    moved = event;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      if (moved) show(moved);
    }, HOVER_WAIT);
  };
  const leave = () => {
    if (timer) clearTimeout(timer);
    timer = undefined;
    moved = null;
    clearHover(refs, setTip);
  };
  const press = (event: PointerEvent) => {
    refs.claim.current = null;
    refs.select.current += 1;
    if (isMuted(refs) || !event.isPrimary || event.button !== 0) {
      return;
    }
    const hovered = refs.target.current ?? refs.hover.current;
    const nearby =
      hovered && Math.hypot(event.clientX - hovered.x, event.clientY - hovered.y) <= 10;
    const match = nearby ? hovered : hit(event);
    const index = match.index;
    if (index == null) return;
    refs.claim.current = {
      committed: false,
      distance: match.distance,
      index,
      paper: nearby ? hovered.paper : undefined,
      pending: true,
      x: event.clientX,
      y: event.clientY,
    };
  };
  const release = (event: MouseEvent | PointerEvent) => pickBound(refs, event);
  const choose = (event: MouseEvent) => {
    const claim = refs.claim.current;
    if (timer) clearTimeout(timer);
    timer = undefined;
    moved = null;
    if (
      isMuted(refs) ||
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
        refs.pick.current(claim.paper);
      }
      window.setTimeout(() => {
        if (refs.claim.current === claim) claim.pending = false;
      }, 0);
      return;
    }
    const token = ++refs.select.current;
    setTip({ label: "Loading Paper…", x: at.x, y: at.y });
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
        claim.committed = true;
        claim.paper = paper;
        claim.pending = false;
        setTip({ label: `Paper · ${paper.paper.title}`, x: at.x, y: at.y });
        refs.pick.current(paper);
      })
      .catch(() => {
        if (token === refs.select.current) {
          setTip({
            label: "Paper details unavailable · select to retry",
            x: at.x,
            y: at.y,
          });
        }
      });
  };

  if (data.scopes.length <= HOVER_LIMIT) canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerleave", leave);
  canvas.addEventListener("pointerdown", press);
  window.addEventListener("pointerup", release, true);
  window.addEventListener("mouseup", release, true);
  canvas.addEventListener("click", choose, true);
  return () => {
    if (timer) clearTimeout(timer);
    controller.abort();
    if (data.scopes.length <= HOVER_LIMIT)
      canvas.removeEventListener("pointermove", move);
    canvas.removeEventListener("pointerleave", leave);
    canvas.removeEventListener("pointerdown", press);
    window.removeEventListener("pointerup", release, true);
    window.removeEventListener("mouseup", release, true);
    canvas.removeEventListener("click", choose, true);
    picker.dispose();
    dropPoints(graph, points, refs, setTip);
  };
}

export function usePoints(input: PointInput): {
  tip: PointTip | null;
  block: () => void;
  drop: () => void;
  mute: (active: boolean) => void;
  take: (node?: GraphNode) => boolean;
} {
  const [tip, setTip] = useState<PointTip | null>(null);
  const pickRef = useRef(input.onPick);
  const blockRef = useRef(0);
  const claimRef = useRef<Claim | null>(null);
  const hoverRef = useRef<Hover | null>(null);
  const muteRef = useRef(false);
  const hiddenRef = useRef(!input.active);
  const pointsRef = useRef<CloudSwarm | null>(null);
  const requestRef = useRef(0);
  const selectRef = useRef(0);
  const targetRef = useRef<Hover | null>(null);
  pickRef.current = input.onPick;
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
  const mute = useCallback((active: boolean) => {
    muteRef.current = active;
    if (!active) return;
    claimRef.current = null;
    hoverRef.current = null;
    targetRef.current = null;
    requestRef.current += 1;
    selectRef.current += 1;
    setTip(null);
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
          mute: muteRef,
          pick: pickRef,
          points: pointsRef,
          request: requestRef,
          select: selectRef,
          target: targetRef,
        },
        setTip,
      ),
    [input.data, input.graphRef],
  );
  useEffect(() => {
    if (pointsRef.current && input.data) growCloud(pointsRef.current, input.data);
  }, [input.data?.loaded]);
  useEffect(() => {
    if (pointsRef.current) paintCloud(pointsRef.current, input.theme);
  }, [input.theme]);
  return { tip, block, drop, mute, take };
}
