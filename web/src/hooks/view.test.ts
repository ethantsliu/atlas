import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CameraView } from "../lib/camera";

let refSlots: Array<{ current: unknown }> = [];
let refIndex = 0;
let frames: FrameRequestCallback[] = [];

vi.mock("react", () => ({
  useCallback: <Value>(callback: Value) => callback,
  useEffect: (effect: () => void | (() => void)) => {
    effect();
  },
  useRef: <Value>(initial?: Value) => {
    const index = refIndex++;
    refSlots[index] ??= { current: initial };
    return refSlots[index];
  },
}));

import { useView } from "./view";

const first: CameraView = {
  target: [12, -8, 30],
  radius: 40,
  yaw: 25,
  pitch: -15,
};

const second: CameraView = {
  target: [-50, 24, 6],
  radius: 20,
  yaw: -40,
  pitch: 10,
};

function fakeGraph(ready = true, controlsReady = true) {
  const canvas = new EventTarget() as HTMLCanvasElement;
  const camera = {
    position: { x: 0, y: 0, z: 100 },
    fov: ready ? 60 : undefined,
  };
  const target = { x: 0, y: 0, z: 0 };
  const control: { target?: typeof target } = {
    target: controlsReady ? target : undefined,
  };
  const cameraPosition = vi.fn(
    (position: Partial<typeof target>, lookAt?: typeof target) => {
      Object.assign(camera.position, position);
      if (lookAt) Object.assign(target, lookAt);
    },
  );
  const graph = {
    camera: () => camera,
    controls: () => control,
    cameraPosition,
    renderer: () => ({ domElement: canvas }),
  };
  return {
    camera,
    cameraPosition,
    canvas,
    control,
    graph,
    graphRef: { current: graph },
    target,
  };
}

function renderHook<Value>(callback: () => Value): Value {
  refIndex = 0;
  return callback();
}

beforeEach(() => {
  refSlots = [];
  refIndex = 0;
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => vi.unstubAllGlobals());

function runFrame() {
  const queued = frames;
  frames = [];
  queued.forEach((callback) => callback(performance.now()));
}

describe("camera restoration", () => {
  it("queues until a render frame and consumes the view once", () => {
    const { cameraPosition, graphRef } = fakeGraph();
    const showView = renderHook(() => useView(graphRef, first, true));
    expect(cameraPosition).not.toHaveBeenCalled();

    showView();
    expect(cameraPosition).toHaveBeenCalledOnce();
    cameraPosition.mockClear();

    showView();
    expect(cameraPosition).not.toHaveBeenCalled();
  });

  it("clears a pending view when URL camera state disappears", () => {
    const { cameraPosition, graphRef } = fakeGraph();
    renderHook(() => useView(graphRef, first, true));
    const showView = renderHook(() => useView(graphRef, null, true));

    showView();
    expect(cameraPosition).not.toHaveBeenCalled();
  });

  it("waits for the final graph data", () => {
    const { cameraPosition, graphRef } = fakeGraph();
    const earlyView = renderHook(() => useView(graphRef, first, false));

    earlyView();
    expect(cameraPosition).not.toHaveBeenCalled();

    const showView = renderHook(() => useView(graphRef, first, true));
    showView();
    expect(cameraPosition).toHaveBeenCalledOnce();
  });

  it("retries a pending view until the graph exists", () => {
    const { cameraPosition, graph } = fakeGraph();
    const graphRef: { current: typeof graph | undefined } = { current: undefined };
    renderHook(() => useView(graphRef, first, true));

    runFrame();
    expect(cameraPosition).not.toHaveBeenCalled();

    graphRef.current = graph;
    runFrame();
    expect(cameraPosition).toHaveBeenCalledOnce();

    runFrame();
    expect(cameraPosition).toHaveBeenCalledOnce();
  });

  it("retries until the graph camera is ready", () => {
    const { camera, cameraPosition, graphRef } = fakeGraph(false);
    renderHook(() => useView(graphRef, first, true));

    runFrame();
    expect(cameraPosition).not.toHaveBeenCalled();

    camera.fov = 60;
    runFrame();
    expect(cameraPosition).toHaveBeenCalledOnce();
  });

  it("retries until the restored camera is readable", () => {
    const { cameraPosition, control, graphRef, target } = fakeGraph(true, false);
    renderHook(() => useView(graphRef, first, true));

    runFrame();
    expect(cameraPosition).toHaveBeenCalledOnce();

    control.target = target;
    runFrame();
    expect(cameraPosition).toHaveBeenCalledTimes(2);

    runFrame();
    expect(cameraPosition).toHaveBeenCalledTimes(2);
  });

  it("keeps user navigation when data finishes loading", () => {
    const { cameraPosition, canvas, graphRef } = fakeGraph();
    renderHook(() => useView(graphRef, first, false));

    canvas.dispatchEvent(new Event("pointerdown"));
    const showView = renderHook(() => useView(graphRef, first, true));
    showView();

    expect(cameraPosition).not.toHaveBeenCalled();
  });

  it("restores later camera state without snapping back", () => {
    const { cameraPosition, graphRef } = fakeGraph();
    const firstView = renderHook(() => useView(graphRef, first, true));
    firstView();
    cameraPosition.mockClear();

    const nextView = renderHook(() => useView(graphRef, second, true));
    nextView();
    expect(cameraPosition).toHaveBeenCalledOnce();
    cameraPosition.mockClear();

    nextView();
    expect(cameraPosition).not.toHaveBeenCalled();
  });
});
