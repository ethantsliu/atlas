import { describe, expect, it, vi } from "vitest";
import {
  cacheMeta,
  clearHover,
  cloudFront,
  hoverMoved,
  hoverWait,
  pickBound,
  pickSize,
  reuseHit,
  shownHit,
} from "./points";

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
    expect(pickSize("mouse")).toBe(8);
    expect(pickSize("touch")).toBe(24);
  });

  it("requires a stable dwell before probing a dense cloud", () => {
    expect(hoverWait(100_000)).toBe(120);
    expect(hoverWait(100_001)).toBe(700);
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
