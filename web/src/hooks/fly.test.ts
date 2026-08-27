import { afterEach, describe, expect, it, vi } from "vitest";

let dispose: void | (() => void);

vi.mock("react", () => ({
  useEffect: (effect: () => void | (() => void)) => {
    dispose = effect();
  },
}));

import { useFly, wheelMove } from "./fly";

afterEach(() => {
  dispose?.();
  dispose = undefined;
});

describe("fly-through wheel input", () => {
  it("keeps fractional pixel deltas used by WebKit trackpads", () => {
    expect(wheelMove(-7.5, 0, 800)).toBeCloseTo(0.0125);
    expect(wheelMove(7.5, 0, 800)).toBeCloseTo(-0.0125);
  });

  it("normalizes line and page units before clamping travel", () => {
    expect(wheelMove(-1, 1, 800)).toBeCloseTo(16 / 600);
    expect(wheelMove(-1, 2, 800)).toBe(0.4);
    expect(wheelMove(-1_200, 0, 800)).toBe(0.4);
    expect(wheelMove(1_200, 0, 800)).toBe(-0.4);
  });

  it("ignores empty and non-finite deltas", () => {
    expect(wheelMove(0, 0, 800)).toBe(0);
    expect(wheelMove(Number.NaN, 0, 800)).toBe(0);
    expect(wheelMove(Number.POSITIVE_INFINITY, 0, 800)).toBe(0);
  });

  it("releases wheel travel at the URL boundary and preserves pinch", () => {
    const canvas = new EventTarget() as HTMLCanvasElement;
    Object.defineProperty(canvas, "clientHeight", { value: 800 });
    const target = { x: 4_096, y: 0, z: 0 };
    const camera = { position: { x: 4_000, y: 0, z: 0 }, fov: 50 };
    const cameraPosition = vi.fn();
    const graph = {
      camera: () => camera,
      controls: () => ({ target }),
      cameraPosition,
      renderer: () => ({ domElement: canvas }),
    };
    useFly({ current: graph });
    const fallback = vi.fn();
    canvas.addEventListener("wheel", fallback);

    const blocked = Object.assign(new Event("wheel", { cancelable: true }), {
      ctrlKey: false,
      deltaMode: 0,
      deltaY: -120,
    }) as WheelEvent;
    canvas.dispatchEvent(blocked);

    expect(blocked.defaultPrevented).toBe(false);
    expect(fallback).toHaveBeenCalledOnce();
    expect(cameraPosition).not.toHaveBeenCalled();

    const pinch = Object.assign(new Event("wheel", { cancelable: true }), {
      ctrlKey: true,
      deltaMode: 0,
      deltaY: -120,
    }) as WheelEvent;
    canvas.dispatchEvent(pinch);

    expect(pinch.defaultPrevented).toBe(false);
    expect(fallback).toHaveBeenCalledTimes(2);
  });
});
