import { describe, expect, it, vi } from "vitest";
import { clearHover, pickBound } from "./points";

const paper = {
  id: "2001.00001",
  title: "Bound paper",
  url: "https://arxiv.org/abs/2001.00001",
  published: "2020-01-01T00:00:00Z",
  scope: "likely" as const,
};
const bound = { index: 4, paper };

describe("paper point hover", () => {
  it("clears stale point identity before the next debounced lookup", () => {
    const hover = { index: 3, x: 20, y: 40 };
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
      target: { current: { index: 3, paper: bound, x: 10, y: 10 } },
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
});
