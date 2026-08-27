import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CameraView } from "../lib/camera";

let refSlots: Array<{ current: unknown }> = [];
let refIndex = 0;

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

function fakeGraph() {
  const canvas = new EventTarget() as HTMLCanvasElement;
  const cameraPosition = vi.fn();
  const graph = {
    camera: () => ({ position: { x: 0, y: 0, z: 100 }, fov: 60 }),
    controls: () => ({ target: { x: 0, y: 0, z: 0 } }),
    cameraPosition,
    renderer: () => ({ domElement: canvas }),
  };
  return { cameraPosition, canvas, graph, graphRef: { current: graph } };
}

function renderHook<Value>(callback: () => Value): Value {
  refIndex = 0;
  return callback();
}

beforeEach(() => {
  refSlots = [];
  refIndex = 0;
});

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
