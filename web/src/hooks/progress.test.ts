import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CloudData } from "../lib/cloud";

type Cleanup = void | (() => void);
type EffectSlot = { cleanup: Cleanup; deps: readonly unknown[] };
type PendingEffect = {
  index: number;
  setup: () => Cleanup;
  deps: readonly unknown[];
};

const swarmMocks = vi.hoisted(() => ({
  CLOUD_REST_MS: 160,
  bindCloud: vi.fn(() => vi.fn()),
  buildCloud: vi.fn(),
  dropCloud: vi.fn(),
  growCloud: vi.fn(),
  paintCloud: vi.fn(),
  restCloud: vi.fn(),
  setCloudDetail: vi.fn(() => false),
}));
const gpuMocks = vi.hoisted(() => ({ makeGpuPick: vi.fn() }));
let activeHarness: HookHarness | null = null;

vi.mock("react", () => ({
  useCallback: <Value>(callback: Value) => callback,
  useEffect: (setup: () => Cleanup, deps: readonly unknown[]) => {
    if (!activeHarness) throw new Error("Hook effect rendered outside its harness");
    activeHarness.useEffect(setup, deps);
  },
  useRef: <Value>(initial: Value) => {
    if (!activeHarness) throw new Error("Hook ref rendered outside its harness");
    return activeHarness.useRef(initial);
  },
  useState: <Value>(initial: Value | (() => Value)) => {
    if (!activeHarness) throw new Error("Hook state rendered outside its harness");
    return activeHarness.useState(initial);
  },
}));

vi.mock("../lib/swarm", () => swarmMocks);
vi.mock("./gpu", () => gpuMocks);

import { usePoints } from "./points";

class HookHarness {
  private states: unknown[] = [];
  private refs: Array<{ current: unknown }> = [];
  private effects: EffectSlot[] = [];
  private pending: PendingEffect[] = [];
  private stateIndex = 0;
  private refIndex = 0;
  private effectIndex = 0;
  private dirty = false;

  useState<Value>(
    initial: Value | (() => Value),
  ): [Value, (next: Value | ((value: Value) => Value)) => void] {
    const index = this.stateIndex++;
    if (!(index in this.states)) {
      this.states[index] =
        typeof initial === "function" ? (initial as () => Value)() : initial;
    }
    const update = (next: Value | ((value: Value) => Value)) => {
      const current = this.states[index] as Value;
      const value =
        typeof next === "function" ? (next as (value: Value) => Value)(current) : next;
      if (Object.is(current, value)) return;
      this.states[index] = value;
      this.dirty = true;
    };
    return [this.states[index] as Value, update];
  }

  useRef<Value>(initial: Value): { current: Value } {
    const index = this.refIndex++;
    this.refs[index] ??= { current: initial };
    return this.refs[index] as { current: Value };
  }

  useEffect(setup: () => Cleanup, deps: readonly unknown[]): void {
    const index = this.effectIndex++;
    const prior = this.effects[index];
    if (
      prior &&
      prior.deps.length === deps.length &&
      prior.deps.every((value, position) => Object.is(value, deps[position]))
    ) {
      return;
    }
    this.pending.push({ index, setup, deps });
  }

  render(input: Parameters<typeof usePoints>[0]): ReturnType<typeof usePoints> {
    let result: ReturnType<typeof usePoints>;
    do {
      this.dirty = false;
      this.stateIndex = 0;
      this.refIndex = 0;
      this.effectIndex = 0;
      this.pending = [];
      activeHarness = this;
      try {
        result = usePoints(input);
      } finally {
        activeHarness = null;
      }
      this.flushEffects();
    } while (this.dirty);
    return result!;
  }

  unmount(): void {
    this.effects.forEach((effect) => effect.cleanup?.());
    this.effects = [];
  }

  state<Value>(index: number): Value {
    return this.states[index] as Value;
  }

  private flushEffects(): void {
    this.pending.forEach(({ index, setup, deps }) => {
      this.effects[index]?.cleanup?.();
      this.effects[index] = { cleanup: setup(), deps };
    });
    this.pending = [];
  }
}

function cloudData(): CloudData {
  return {
    positions: new Float32Array(12),
    scopes: new Uint8Array(4),
    ranges: [],
    loaded: 0,
    radius: 0,
  };
}

function pointEvent(
  type: string,
  x = 10,
  y = 10,
  pointerType = "mouse",
  isPrimary = true,
): Event {
  const event = new Event(type);
  Object.assign(event, {
    button: 0,
    clientX: x,
    clientY: y,
    isPrimary,
    pointerType,
  });
  return event;
}

beforeEach(() => {
  activeHarness = null;
  vi.clearAllMocks();
  const fakeWindow = new EventTarget() as EventTarget & typeof globalThis;
  Object.assign(fakeWindow, { setTimeout });
  vi.stubGlobal("window", fakeWindow);
});

afterEach(() => vi.unstubAllGlobals());

describe("progressive point mounting", () => {
  it("grows and repaints one mounted cloud without rebuilding it", () => {
    const canvas = new EventTarget() as HTMLCanvasElement;
    const renderer = { domElement: canvas, render: vi.fn() };
    const scene = { add: vi.fn(), remove: vi.fn() };
    const camera = {};
    const graph = {
      camera: () => camera,
      renderer: () => renderer,
      scene: () => scene,
    };
    const points = {
      geometry: { dispose: vi.fn() },
      material: { dispose: vi.fn() },
      visible: true,
    };
    const picker = { dispose: vi.fn(), pick: vi.fn() };
    swarmMocks.buildCloud.mockReturnValue(points);
    gpuMocks.makeGpuPick.mockReturnValue(picker);
    const data = cloudData();
    const harness = new HookHarness();
    const base = {
      graphRef: { current: graph },
      data,
      active: true,
      theme: "light" as const,
      onPick: vi.fn(),
    } as unknown as Parameters<typeof usePoints>[0];

    harness.render(base);
    expect(swarmMocks.buildCloud).toHaveBeenCalledOnce();
    const redraw = swarmMocks.buildCloud.mock.calls[0][3] as () => void;
    redraw();
    expect(renderer.render).toHaveBeenCalledWith(scene, camera);
    expect(scene.add).toHaveBeenCalledOnce();
    expect(swarmMocks.growCloud).toHaveBeenCalledWith(points, data);

    data.loaded = 2;
    harness.render(base);
    expect(swarmMocks.buildCloud).toHaveBeenCalledOnce();
    expect(scene.add).toHaveBeenCalledOnce();
    expect(scene.remove).not.toHaveBeenCalled();
    expect(swarmMocks.growCloud).toHaveBeenLastCalledWith(points, data);

    data.loaded = 4;
    harness.render({ ...base, theme: "dark" });
    expect(swarmMocks.buildCloud).toHaveBeenCalledOnce();
    expect(swarmMocks.growCloud).toHaveBeenLastCalledWith(points, data);
    expect(swarmMocks.paintCloud).toHaveBeenLastCalledWith(points, "dark");

    harness.unmount();
    expect(scene.remove).toHaveBeenCalledOnce();
    expect(swarmMocks.dropCloud).toHaveBeenCalledWith(points);
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it("clears a dense hover hold when the point layer is torn down", () => {
    const canvas = new EventTarget() as HTMLCanvasElement;
    const renderer = { domElement: canvas };
    const scene = { add: vi.fn(), remove: vi.fn() };
    const graph = { camera: () => ({}), renderer: () => renderer, scene: () => scene };
    const points = {
      geometry: { dispose: vi.fn() },
      material: { dispose: vi.fn() },
      userData: { moving: false },
      visible: true,
    };
    swarmMocks.buildCloud.mockReturnValue(points);
    gpuMocks.makeGpuPick.mockReturnValue({ dispose: vi.fn(), pick: vi.fn() });
    const data = cloudData();
    data.loaded = 100_001;
    const harness = new HookHarness();
    const input = {
      active: true,
      data,
      graphRef: { current: graph },
      onPick: vi.fn(),
      order: { begin: vi.fn(), claim: vi.fn() },
      theme: "light",
    } as unknown as Parameters<typeof usePoints>[0];

    harness.render(input);
    canvas.dispatchEvent(pointEvent("pointermove"));
    expect(harness.render(input).probing).toBe(true);

    harness.unmount();
    expect(harness.state<boolean>(1)).toBe(false);
  });

  it("discards a pending click after a newer pointer claim", async () => {
    const canvas = new EventTarget() as HTMLCanvasElement;
    canvas["getBoundingClientRect"] = () =>
      ({ height: 100, left: 0, top: 0, width: 100 }) as DOMRect;
    const renderer = { domElement: canvas };
    const scene = { add: vi.fn(), remove: vi.fn() };
    const graph = { camera: () => ({}), renderer: () => renderer, scene: () => scene };
    const points = {
      geometry: { dispose: vi.fn() },
      material: { dispose: vi.fn() },
      visible: true,
    };
    let resolvePick!: (value: unknown) => void;
    const pick = vi.fn(() => new Promise((resolve) => (resolvePick = resolve)));
    const picker = { dispose: vi.fn(), pick };
    const order = { begin: vi.fn(), claim: vi.fn() };
    swarmMocks.buildCloud.mockReturnValue(points);
    gpuMocks.makeGpuPick.mockReturnValue(picker);
    const data = cloudData();
    data.loaded = 1;
    const harness = new HookHarness();
    harness.render({
      active: true,
      data,
      graphRef: { current: graph },
      onPick: vi.fn(),
      order,
      theme: "light",
    } as unknown as Parameters<typeof usePoints>[0]);

    canvas.dispatchEvent(pointEvent("pointerdown"));
    window.dispatchEvent(pointEvent("pointerup"));
    canvas.dispatchEvent(pointEvent("click", 10, 10, "mouse", false));
    expect(pick).toHaveBeenCalledOnce();
    expect(swarmMocks.restCloud).toHaveBeenCalledWith(points);

    canvas.dispatchEvent(pointEvent("pointerdown", 12, 10));
    resolvePick({ distance: 1, index: 0, valid: () => true });
    await Promise.resolve();
    await Promise.resolve();

    expect(order.claim).not.toHaveBeenCalled();
    harness.unmount();
  });

  it("keeps one touch pick through slow camera settling", async () => {
    const canvas = new EventTarget() as HTMLCanvasElement;
    canvas["getBoundingClientRect"] = () =>
      ({ height: 100, left: 0, top: 0, width: 100 }) as DOMRect;
    const renderer = { domElement: canvas };
    const scene = { add: vi.fn(), remove: vi.fn() };
    const controls = new EventTarget();
    const graph = {
      camera: () => ({}),
      controls: () => controls,
      renderer: () => renderer,
      scene: () => scene,
    };
    const points = {
      geometry: { dispose: vi.fn() },
      material: { dispose: vi.fn() },
      userData: { moving: true },
      visible: true,
    };
    const pick = vi.fn().mockResolvedValue({
      distance: 1,
      index: 0,
      valid: () => true,
    });
    const picker = { dispose: vi.fn(), pick };
    const order = { begin: vi.fn(), claim: vi.fn() };
    const retries: Array<() => void> = [];
    window.setTimeout = vi.fn((run: TimerHandler) => {
      retries.push(run as () => void);
      return 1;
    }) as unknown as typeof window.setTimeout;
    swarmMocks.buildCloud.mockReturnValue(points);
    gpuMocks.makeGpuPick.mockReturnValue(picker);
    const data = cloudData();
    data.loaded = 1;
    const harness = new HookHarness();
    harness.render({
      active: true,
      data,
      graphRef: { current: graph },
      onPick: vi.fn(),
      order,
      theme: "light",
    } as unknown as Parameters<typeof usePoints>[0]);

    canvas.dispatchEvent(pointEvent("pointerdown", 10, 10, "touch"));
    controls.dispatchEvent(new Event("change"));
    window.dispatchEvent(pointEvent("pointerup", 10, 10, "touch"));
    canvas.dispatchEvent(pointEvent("pointerleave", 10, 10, "touch"));
    controls.dispatchEvent(new Event("change"));
    canvas.dispatchEvent(pointEvent("click"));
    controls.dispatchEvent(new Event("change"));
    expect(pick).not.toHaveBeenCalled();

    for (let retry = 0; retry < 4; retry += 1) {
      retries.shift()?.();
      expect(pick).not.toHaveBeenCalled();
    }
    points.userData.moving = false;
    retries.shift()?.();
    await Promise.resolve();
    await Promise.resolve();

    expect(pick).toHaveBeenCalledOnce();
    expect(pick.mock.calls[0][4]).toBe(44);
    expect(order.claim).toHaveBeenCalledOnce();
    harness.unmount();
  });
});
