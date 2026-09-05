import { describe, expect, it, vi } from "vitest";
import {
  cacheMeta,
  canHoverCloud,
  clearHover,
  cloudFront,
  hoverMoved,
  hoverWait,
  pickBound,
  pickSize,
  reuseHit,
  shownHit,
  waitHoverRest,
} from "./points";
import { choosePoint, showPoint } from "./probe";

const paper = {
  id: "2001.00001",
  title: "Bound paper",
  url: "https://arxiv.org/abs/2001.00001",
  published: "2020-01-01T00:00:00Z",
  scope: "likely" as const,
};
const bound = { index: 4, paper };

describe("paper point input", () => {
  it("keeps dense points usable with touch-sized picking", () => {
    expect(pickSize("mouse")).toBe(12);
    expect(pickSize("touch")).toBe(44);
  });

  it("keeps dense hover off the active rotation path", () => {
    expect(hoverWait(100_000)).toBe(120);
    expect(hoverWait(100_001)).toBe(700);
    expect(canHoverCloud(100_000, true)).toBe(true);
    expect(canHoverCloud(100_001, true)).toBe(false);
    expect(canHoverCloud(100_001, false)).toBe(true);
    expect(waitHoverRest(true, 0)).toBe(true);
    expect(waitHoverRest(true, 13)).toBe(true);
    expect(waitHoverRest(true, 14)).toBe(false);
    expect(waitHoverRest(false, 0)).toBe(false);
  });

  it("keeps dense probing busy until paper metadata settles", async () => {
    let resolveLoad!: (value: typeof bound) => void;
    const load = vi.fn(
      () => new Promise<typeof bound>((resolve) => (resolveLoad = resolve)),
    );
    const setProbing = vi.fn();
    const setTip = vi.fn();
    const refs = {
      block: { current: 0 },
      claim: { current: null },
      hidden: { current: false },
      hover: { current: null },
      pick: { current: vi.fn() },
      points: { current: null },
      request: { current: 0 },
      select: { current: 0 },
      target: { current: null },
    };
    const event = {
      clientX: 10,
      clientY: 20,
    } as PointerEvent;

    await showPoint({
      event,
      hit: async () => ({ distance: 1, index: 4, x: 10, y: 20 }),
      load,
      refs,
      setProbing,
      setTip,
    });

    expect(setTip).toHaveBeenLastCalledWith({
      depth: 1,
      label: "Loading Paper…",
      x: 10,
      y: 20,
    });
    expect(setProbing).not.toHaveBeenCalled();

    resolveLoad(bound);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(setTip).toHaveBeenLastCalledWith({
      depth: 1,
      label: `Paper · ${paper.title}`,
      x: 10,
      y: 20,
    });
    expect(setProbing).toHaveBeenCalledOnce();
    expect(setProbing).toHaveBeenCalledWith(false);
  });

  it("releases dense probing when paper metadata fails", async () => {
    const setProbing = vi.fn();
    const setTip = vi.fn();
    const refs = {
      block: { current: 0 },
      claim: { current: null },
      hidden: { current: false },
      hover: { current: null },
      pick: { current: vi.fn() },
      points: { current: null },
      request: { current: 0 },
      select: { current: 0 },
      target: { current: null },
    };

    await showPoint({
      event: { clientX: 10, clientY: 20 } as PointerEvent,
      hit: async () => ({ distance: 1, index: 4, x: 10, y: 20 }),
      load: async () => {
        throw new Error("bad metadata");
      },
      refs,
      setProbing,
      setTip,
    });
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(setTip).toHaveBeenLastCalledWith({
      depth: 1,
      label: "Paper details unavailable · hover to retry",
      x: 10,
      y: 20,
    });
    expect(setProbing).toHaveBeenLastCalledWith(false);
  });

  it("keeps a click claim busy until paper metadata settles", async () => {
    let resolveLoad!: (value: typeof bound) => void;
    const setProbing = vi.fn();
    const setTip = vi.fn();
    const refs = {
      block: { current: 0 },
      claim: { current: null },
      hidden: { current: false },
      hover: { current: null },
      pick: { current: vi.fn() },
      points: { current: null },
      request: { current: 0 },
      select: { current: 0 },
      target: { current: null },
    };
    const event = { button: 0, clientX: 10, clientY: 20 } as MouseEvent;
    const bounds = () => ({ left: 0, top: 0 });
    const canvas = {
      getBoundingClientRect: bounds,
    } as HTMLCanvasElement;
    const order = {
      claim: vi.fn((_rank, _depth, commit: () => void) => commit()),
    };

    choosePoint({
      canvas,
      event,
      hit: async () => ({ distance: 1, index: 4, x: 10, y: 20 }),
      load: () => new Promise<typeof bound>((resolve) => (resolveLoad = resolve)),
      order: order as never,
      refs,
      setProbing,
      setTip,
      start: { x: 10, y: 20 },
      token: 0,
    });
    await Promise.resolve();
    await Promise.resolve();

    expect(setProbing).toHaveBeenLastCalledWith(true);
    expect(setTip).toHaveBeenLastCalledWith({
      depth: 1,
      label: "Loading Paper…",
      x: 10,
      y: 20,
    });

    resolveLoad(bound);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(setProbing).toHaveBeenLastCalledWith(false);
  });

  it("hides a stale dense-cloud label after meaningful pointer movement", () => {
    const hover = { x: 20, y: 40 };

    expect(hoverMoved(hover, { clientX: 20, clientY: 40 })).toBe(false);
    expect(hoverMoved(hover, { clientX: 21, clientY: 40 })).toBe(true);
    expect(hoverMoved(null, { clientX: 40, clientY: 40 })).toBe(false);
  });

  it("reuses only an exact still-valid hover pick", () => {
    const valid = vi.fn(() => true);
    const hover = { valid, x: 20, y: 40 };

    expect(reuseHit(hover, { clientX: 20, clientY: 40 })).toBe(true);
    expect(reuseHit(hover, { clientX: 21, clientY: 40 })).toBe(false);
    valid.mockReturnValue(false);
    expect(reuseHit(hover, { clientX: 20, clientY: 40 })).toBe(false);
  });

  it("keeps an exact displayed paper clickable after passive camera drift", () => {
    const hover = { paper: bound, x: 20, y: 40 };

    expect(shownHit(hover, { clientX: 20, clientY: 40 })).toBe(true);
    expect(shownHit(hover, { clientX: 20, clientY: 40.5 })).toBe(true);
    expect(shownHit(hover, { clientX: 21.1, clientY: 40 })).toBe(false);
    expect(shownHit({ ...hover, paper: undefined }, { clientX: 20, clientY: 40 })).toBe(
      false,
    );
  });

  it("bounds metadata to two recently used shards", async () => {
    const cache = new Map<string, Promise<number>>();
    for (let index = 0; index < 5; index += 1) {
      await cacheMeta(cache, `${index}`, async () => index);
    }
    cacheMeta(cache, "1", async () => 9);
    cacheMeta(cache, "5", async () => 5);

    expect([...cache.keys()]).toEqual(["1", "5"]);
  });

  it("keeps the visually nearer layer", () => {
    const graph = {
      camera: () => ({ position: { x: 0, y: 0, z: 0 } }),
    } as never;
    const node = { id: "topic", kind: "topic", x: 0, y: 0, z: 10 } as never;

    expect(cloudFront(graph, node, 8)).toBe(true);
    expect(cloudFront(graph, node, 12)).toBe(false);
  });

  it("clears stale point identity before the next debounced lookup", () => {
    const hover = { distance: 1, index: 3, x: 20, y: 40 };
    const target = { ...hover, paper: undefined };
    const refs = {
      hover: { current: hover },
      request: { current: 7 },
      target: { current: target },
    };
    const setTip = vi.fn();

    clearHover(refs, setTip);

    expect(refs.hover.current).toBeNull();
    expect(refs.target.current).toBeNull();
    expect(refs.request.current).toBe(8);
    expect(setTip).toHaveBeenCalledOnce();
    expect(setTip).toHaveBeenCalledWith(null);
  });

  it("never binds metadata from a different point index", () => {
    const pick = vi.fn();
    const refs = {
      block: { current: 0 },
      claim: {
        current: {
          committed: false,
          distance: 1,
          index: 4,
          pending: true,
          x: 10,
          y: 10,
        },
      },
      hover: { current: null },
      pick: { current: pick },
      request: { current: 0 },
      select: { current: 0 },
      target: {
        current: { distance: 1, index: 3, paper: bound, x: 10, y: 10 },
      },
    };
    const event = {
      button: 0,
      clientX: 10,
      clientY: 10,
      isPrimary: true,
    } as PointerEvent;

    pickBound(refs, event);

    expect(pick).not.toHaveBeenCalled();
  });

  it("commits one resolved point only once", () => {
    const pick = vi.fn();
    const refs = {
      block: { current: 0 },
      claim: {
        current: {
          committed: false,
          distance: 1,
          index: 4,
          paper: bound,
          pending: true,
          x: 10,
          y: 10,
        },
      },
      hover: { current: null },
      pick: { current: pick },
      request: { current: 0 },
      select: { current: 0 },
      target: { current: null },
    };
    const event = {
      button: 0,
      clientX: 10,
      clientY: 10,
      isPrimary: true,
    } as PointerEvent;

    pickBound(refs, event);
    pickBound(refs, event);

    expect(pick).toHaveBeenCalledOnce();
  });

  it("commits a resolved point from a primary touch", () => {
    const pick = vi.fn();
    const refs = {
      claim: {
        current: {
          committed: false,
          distance: 1,
          index: 4,
          paper: bound,
          pending: true,
          x: 10,
          y: 10,
        },
      },
      pick: { current: pick },
      target: { current: null },
    };
    const event = {
      button: 0,
      clientX: 10,
      clientY: 10,
      isPrimary: true,
      pointerType: "touch",
    } as PointerEvent;

    pickBound(refs, event);

    expect(pick).toHaveBeenCalledOnce();
    expect(pick).toHaveBeenCalledWith(bound, 1);
  });

  it("rejects a touch drag across the paper cloud", () => {
    const pick = vi.fn();
    const refs = {
      claim: {
        current: {
          committed: false,
          distance: 1,
          index: 4,
          paper: bound,
          pending: true,
          x: 10,
          y: 10,
        },
      },
      pick: { current: pick },
      target: { current: null },
    };
    const event = {
      button: 0,
      clientX: 18,
      clientY: 10,
      isPrimary: true,
      pointerType: "touch",
    } as PointerEvent;

    pickBound(refs, event);

    expect(pick).not.toHaveBeenCalled();
  });
});
