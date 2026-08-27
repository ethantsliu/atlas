import { useCallback, useEffect, useRef, useState } from "react";
import { Raycaster, Vector2, type Camera, type Points } from "three";
import type { GraphRef } from "../components/map/Driver";
import {
  cloudPaper,
  cloudRange,
  fetchCloudMeta,
  type CloudData,
  type CloudPaper,
} from "../lib/cloud";
import { buildCloud } from "../lib/swarm";
import type { Theme } from "./theme";

const HOVER_LIMIT = 100_000;
const HOVER_WAIT = 120;

export type PointTip = { label: string; x: number; y: number };

type PointInput = {
  graphRef: GraphRef;
  data: CloudData | null;
  theme: Theme;
  onPick: (paper: CloudPaper) => void;
};
type Claim = {
  committed: boolean;
  index: number;
  paper?: CloudPaper;
  pending: boolean;
  x: number;
  y: number;
};
type Hover = { index: number; paper?: CloudPaper; x: number; y: number };
type Ref<T> = { current: T };
type PointRefs = {
  block: Ref<number>;
  claim: Ref<Claim | null>;
  hover: Ref<Hover | null>;
  mute: Ref<boolean>;
  pick: Ref<(paper: CloudPaper) => void>;
  request: Ref<number>;
  select: Ref<number>;
  target: Ref<Hover | null>;
};

function rayHit(
  canvas: HTMLCanvasElement,
  graph: NonNullable<GraphRef["current"]>,
  points: Points,
  raycaster: Raycaster,
  pointer: Vector2,
  event: PointerEvent | MouseEvent,
) {
  const rect = canvas.getBoundingClientRect();
  pointer.set(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
  const camera = graph.camera() as Camera;
  raycaster.params.Points = {
    threshold: Math.max(2.5, camera.position.length() / 180),
  };
  raycaster.setFromCamera(pointer, camera);
  const index = raycaster.intersectObject(points, false)[0]?.index;
  return {
    index: typeof index === "number" ? index : null,
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

async function loadPaper(
  data: CloudData,
  cache: Map<string, Promise<CloudPaper[]>>,
  signal: AbortSignal,
  index: number,
) {
  const range = cloudRange(data, index);
  if (!range) return null;
  let request = cache.get(range.meta.path);
  if (!request) {
    request = fetchCloudMeta(range, signal);
    cache.set(range.meta.path, request);
    void request.catch(() => cache.delete(range.meta.path));
  }
  return cloudPaper(await request, range, index);
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

function mountPoints(
  input: PointInput,
  refs: PointRefs,
  setTip: (tip: PointTip | null) => void,
) {
  const graph = input.graphRef.current;
  const data = input.data;
  if (!graph || !data || data.scopes.length === 0) return;
  const points = buildCloud(data, input.theme);
  graph.scene().add(points);
  const canvas = graph.renderer().domElement;
  const raycaster = new Raycaster();
  const pointer = new Vector2();
  const controller = new AbortController();
  const cache = new Map<string, Promise<CloudPaper[]>>();
  const hit = (event: PointerEvent | MouseEvent) =>
    rayHit(canvas, graph, points, raycaster, pointer, event);
  const load = (index: number) => loadPaper(data, cache, controller.signal, index);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let moved: PointerEvent | null = null;

  const show = (event: PointerEvent) => {
    if (refs.mute.current || performance.now() < refs.block.current) return;
    const match = hit(event);
    const token = ++refs.request.current;
    if (match.index == null) {
      clearHover(refs, setTip);
      return;
    }
    const index = match.index;
    refs.hover.current = { index, x: event.clientX, y: event.clientY };
    setTip({ label: "Loading Paper…", x: match.x, y: match.y });
    void load(index)
      .then((paper) => {
        if (!paper || token !== refs.request.current) return;
        if (refs.hover.current?.index === index) refs.hover.current.paper = paper;
        refs.target.current = {
          index,
          paper,
          x: event.clientX,
          y: event.clientY,
        };
        setTip({ label: `Paper · ${paper.title}`, x: match.x, y: match.y });
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
    if (refs.mute.current) {
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
    if (refs.mute.current || !event.isPrimary || event.button !== 0) return;
    const hovered = refs.target.current ?? refs.hover.current;
    const nearby =
      hovered && Math.hypot(event.clientX - hovered.x, event.clientY - hovered.y) <= 10;
    const index = nearby ? hovered.index : hit(event).index;
    if (index == null) return;
    refs.claim.current = {
      committed: false,
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
      refs.mute.current ||
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
        setTip({ label: `Paper · ${paper.title}`, x: at.x, y: at.y });
        refs.pick.current(paper);
      })
      .catch(() => {
        if (token === refs.select.current) {
          setTip({
            label: "Paper details unavailable · click to retry",
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
    graph.scene().remove(points);
    points.geometry.dispose();
    points.material.dispose();
    refs.claim.current = null;
    refs.hover.current = null;
    refs.target.current = null;
    refs.request.current += 1;
    refs.select.current += 1;
    setTip(null);
  };
}

export function usePoints(input: PointInput): {
  tip: PointTip | null;
  block: () => void;
  drop: () => void;
  mute: (active: boolean) => void;
  take: () => boolean;
} {
  const [tip, setTip] = useState<PointTip | null>(null);
  const pickRef = useRef(input.onPick);
  const blockRef = useRef(0);
  const claimRef = useRef<Claim | null>(null);
  const hoverRef = useRef<Hover | null>(null);
  const muteRef = useRef(false);
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
  const take = useCallback(() => {
    const claim = claimRef.current;
    return Boolean(claim?.pending && claim.paper);
  }, []);
  useEffect(
    () =>
      mountPoints(
        input,
        {
          block: blockRef,
          claim: claimRef,
          hover: hoverRef,
          mute: muteRef,
          pick: pickRef,
          request: requestRef,
          select: selectRef,
          target: targetRef,
        },
        setTip,
      ),
    [input.data, input.graphRef, input.theme],
  );
  return { tip, block, drop, mute, take };
}
