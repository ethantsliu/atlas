import type { CloudPick } from "../lib/cloud";
import type { PickOrder } from "../lib/order";
import { CLOUD_REST_MS, type CloudSwarm } from "../lib/swarm";

const CLICK_SETTLE_TRIES = 20;
const CLICK_EMPTY_TRIES = 3;

export type PointTip = { depth: number; label: string; x: number; y: number };

export type Claim = {
  committed: boolean;
  distance: number;
  index: number;
  paper?: CloudPick;
  pending: boolean;
  valid?: () => boolean;
  x: number;
  y: number;
};

export type Hover = {
  distance: number;
  index: number;
  paper?: CloudPick;
  valid?: () => boolean;
  x: number;
  y: number;
};

type Ref<T> = { current: T };

export type PointRefs = {
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

export type PointMatch = {
  distance: number;
  index: number | null;
  paper?: CloudPick;
  valid?: () => boolean;
  x: number;
  y: number;
};

type PointHit<Event extends MouseEvent | PointerEvent> = (
  event: Event,
  pointer?: string,
) => Promise<PointMatch>;

type PointLoad = (index: number) => Promise<CloudPick | null>;

type ClickInput = {
  cached?: Hover;
  canvas: HTMLCanvasElement;
  done?: () => void;
  event: MouseEvent;
  hit: PointHit<MouseEvent>;
  load: PointLoad;
  order: PickOrder;
  pointer?: string;
  refs: PointRefs;
  setProbing: (value: boolean) => void;
  setTip: (tip: PointTip | null) => void;
  start: { x: number; y: number };
  token: number;
  tries?: number;
  misses?: number;
};

type ShowInput = {
  event: PointerEvent;
  hit: PointHit<PointerEvent>;
  load: PointLoad;
  refs: PointRefs;
  setProbing: (value: boolean) => void;
  setTip: (tip: PointTip | null) => void;
};

export function isHidden(refs: Pick<PointRefs, "hidden">): boolean {
  return refs.hidden.current;
}

export function pickBound(
  refs: Pick<PointRefs, "claim" | "pick" | "target">,
  event: MouseEvent | PointerEvent,
): void {
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
): void {
  refs.hover.current = null;
  refs.target.current = null;
  refs.request.current += 1;
  setTip(null);
}

export function reuseHit(
  hover: Pick<Hover, "valid" | "x" | "y"> | null,
  event: Pick<MouseEvent, "clientX" | "clientY">,
): boolean {
  return Boolean(
    hover && hover.x === event.clientX && hover.y === event.clientY && hover.valid?.(),
  );
}

export function shownHit(
  hover: Pick<Hover, "paper" | "x" | "y"> | null,
  event: Pick<MouseEvent, "clientX" | "clientY">,
): boolean {
  return Boolean(
    hover?.paper && Math.hypot(hover.x - event.clientX, hover.y - event.clientY) <= 1,
  );
}

function hoverAt(
  match: Pick<Hover, "distance" | "index" | "valid">,
  event: PointerEvent,
): Hover {
  return { ...match, x: event.clientX, y: event.clientY };
}

function queueClaim(
  order: PickOrder,
  refs: PointRefs,
  setTip: (tip: PointTip | null) => void,
  load: PointLoad,
  setProbing: (value: boolean) => void,
  claim: Claim,
  at: { x: number; y: number },
): void {
  order.claim(1, claim.distance, () => {
    if (claim.valid && !claim.valid()) {
      claim.pending = false;
      return;
    }
    const token = ++refs.select.current;
    claim.committed = true;
    setProbing(true);
    setTip({ depth: claim.distance, label: "Loading Paper…", ...at });
    void load(claim.index)
      .then((paper) => {
        if (
          !paper ||
          token !== refs.select.current ||
          refs.claim.current !== claim ||
          (claim.valid && !claim.valid()) ||
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
      })
      .finally(() => {
        if (token === refs.select.current) setProbing(false);
      });
  });
}

export async function showPoint(args: ShowInput): Promise<void> {
  const { event, hit, load, refs, setProbing, setTip } = args;
  if (isHidden(refs) || performance.now() < refs.block.current) {
    setProbing(false);
    return;
  }
  const token = ++refs.request.current;
  let match: PointMatch;
  try {
    match = await hit(event);
  } catch {
    if (token === refs.request.current) {
      clearHover(refs, setTip);
      setProbing(false);
    }
    return;
  }
  if (
    token !== refs.request.current ||
    isHidden(refs) ||
    performance.now() < refs.block.current
  ) {
    return;
  }
  if (match.index == null) {
    setProbing(false);
    clearHover(refs, setTip);
    return;
  }
  const index = match.index;
  const picked = { distance: match.distance, index, valid: match.valid };
  refs.hover.current = hoverAt(picked, event);
  setTip({ depth: match.distance, label: "Loading Paper…", x: match.x, y: match.y });
  void load(index)
    .then((paper) => {
      if (!paper || token !== refs.request.current) return;
      if (refs.hover.current?.index === index) refs.hover.current.paper = paper;
      refs.target.current = { ...hoverAt(picked, event), paper };
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
    })
    .finally(() => {
      if (token === refs.request.current) setProbing(false);
    });
}

function claimPoint(args: ClickInput, match: PointMatch): void {
  const { canvas, event, load, order, refs, setTip, start, token } = args;
  if (token !== refs.select.current || isHidden(refs) || match.index == null) return;
  const hovered = refs.target.current ?? refs.hover.current;
  const paper =
    match.paper ?? (hovered?.index === match.index ? hovered.paper : undefined);
  if (performance.now() < refs.block.current && !paper) return;
  const claim: Claim = {
    committed: false,
    distance: match.distance,
    index: match.index,
    paper,
    pending: true,
    valid: match.valid,
    ...start,
  };
  refs.claim.current = claim;
  if (paper) {
    pickBound(refs, event);
    window.setTimeout(() => {
      if (refs.claim.current === claim) claim.pending = false;
    }, 0);
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const at = { x: event.clientX - rect.left, y: event.clientY - rect.top };
  queueClaim(order, refs, setTip, load, args.setProbing, claim, at);
}

export function choosePoint(args: ClickInput): void {
  const { canvas, event, hit, refs, token } = args;
  const cached = args.cached ?? refs.target.current;
  if (shownHit(cached, event) || reuseHit(cached, event)) {
    const rect = canvas.getBoundingClientRect();
    claimPoint(args, {
      distance: cached!.distance,
      index: cached!.index,
      paper: cached!.paper,
      valid: cached!.valid,
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    });
    args.done?.();
    return;
  }
  if (refs.points.current?.userData?.moving) {
    const tries = args.tries ?? 0;
    if (tries >= CLICK_SETTLE_TRIES) {
      args.done?.();
      return;
    }
    window.setTimeout(() => {
      if (token !== refs.select.current || isHidden(refs)) {
        args.done?.();
        return;
      }
      choosePoint({ ...args, tries: tries + 1 });
    }, CLOUD_REST_MS + 20);
    return;
  }
  void hit(event, args.pointer)
    .then((match) => {
      const misses = args.misses ?? 0;
      if (
        match.index == null &&
        args.pointer === "touch" &&
        misses < CLICK_EMPTY_TRIES &&
        token === refs.select.current &&
        !isHidden(refs)
      ) {
        window.setTimeout(
          () => choosePoint({ ...args, misses: misses + 1 }),
          CLOUD_REST_MS + 20,
        );
        return false;
      }
      claimPoint(args, match);
      return true;
    })
    .catch(() => {
      if (token === refs.select.current) refs.claim.current = null;
      return true;
    })
    .then((done) => {
      if (done) args.done?.();
    });
}
