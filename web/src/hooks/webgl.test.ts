import { beforeEach, describe, expect, it, vi } from "vitest";

type StateSetter<Value> = (next: Value | ((value: Value) => Value)) => void;

let stateSlots: unknown[] = [];
let refSlots: Array<{ current: unknown }> = [];
let stateIndex = 0;
let refIndex = 0;

vi.mock("react", () => ({
  useCallback: <Value>(callback: Value) => callback,
  useEffect: () => undefined,
  useRef: <Value>(initial?: Value) => {
    const index = refIndex++;
    refSlots[index] ??= { current: initial };
    return refSlots[index];
  },
  useState: <Value>(initial: Value | (() => Value)) => {
    const index = stateIndex++;
    if (!(index in stateSlots)) {
      stateSlots[index] =
        typeof initial === "function" ? (initial as () => Value)() : initial;
    }
    const setState: StateSetter<Value> = (next) => {
      const current = stateSlots[index] as Value;
      stateSlots[index] =
        typeof next === "function" ? (next as (value: Value) => Value)(current) : next;
    };
    return [stateSlots[index], setState];
  },
}));

import { probeWebgl, useWebgl, watchCanvas } from "./webgl";

function renderHook() {
  stateIndex = 0;
  refIndex = 0;
  return useWebgl({ current: null });
}

beforeEach(() => {
  stateSlots = [];
  refSlots = [];
  stateIndex = 0;
  refIndex = 0;
  vi.unstubAllGlobals();
});

function fakeCanvas(context: WebGL2RenderingContext | null = null): HTMLCanvasElement {
  const canvas = new EventTarget() as HTMLCanvasElement;
  canvas.getContext = vi.fn(() => context) as typeof canvas.getContext;
  return canvas;
}

describe("probeWebgl", () => {
  it("accepts WebGL2 and releases its probe context", () => {
    const loseContext = vi.fn();
    const context = {
      getExtension: vi.fn(() => ({ loseContext })),
    } as unknown as WebGL2RenderingContext;

    expect(probeWebgl(() => fakeCanvas(context))).toBe(true);
    expect(context.getExtension).toHaveBeenCalledWith("WEBGL_lose_context");
    expect(loseContext).toHaveBeenCalledOnce();
  });

  it("falls back when WebGL2 is absent or probing throws", () => {
    expect(probeWebgl(() => fakeCanvas())).toBe(false);
    expect(
      probeWebgl(() => {
        throw new Error("canvas unavailable");
      }),
    ).toBe(false);
  });
});

describe("watchCanvas", () => {
  it("cancels context loss and reports loss and restoration", () => {
    const canvas = fakeCanvas();
    const lost = vi.fn();
    const restored = vi.fn();
    const cleanup = watchCanvas(canvas, { lost, restored });
    const loss = new Event("webglcontextlost", { cancelable: true });

    canvas.dispatchEvent(loss);
    canvas.dispatchEvent(new Event("webglcontextrestored"));

    expect(loss.defaultPrevented).toBe(true);
    expect(lost).toHaveBeenCalledOnce();
    expect(restored).toHaveBeenCalledOnce();

    cleanup();
    canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
    expect(lost).toHaveBeenCalledOnce();
  });
});

describe("useWebgl", () => {
  it("probes once initially and once for each explicit retry", () => {
    const loseContext = vi.fn();
    const getContext = vi.fn(() => ({
      getExtension: () => ({ loseContext }),
    }));
    const createElement = vi.fn(() => ({ getContext }));
    vi.stubGlobal("document", { createElement });
    vi.stubGlobal("window", {
      clearTimeout: vi.fn(),
      setTimeout: (callback: () => void) => {
        callback();
        return 1;
      },
    });

    expect(renderHook().mode).toBe("3d");
    expect(renderHook().mode).toBe("3d");
    expect(createElement).toHaveBeenCalledOnce();

    renderHook().retry();
    expect(renderHook()).toMatchObject({ mode: "3d", status: "ready" });
    expect(createElement).toHaveBeenCalledTimes(2);
    expect(loseContext).toHaveBeenCalledTimes(2);
  });
});
