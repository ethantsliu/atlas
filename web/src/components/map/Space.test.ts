import { describe, expect, it, vi } from "vitest";

vi.mock("react-force-graph-3d", () => ({ default: () => null }));

const cloudMocks = vi.hoisted(() => ({
  moveCloud: vi.fn(),
  restCloud: vi.fn(),
}));

vi.mock("../../lib/swarm", async () => ({
  ...(await vi.importActual<typeof import("../../lib/swarm")>("../../lib/swarm")),
  ...cloudMocks,
}));

import { FRAME_IDLE_WAIT, makeFrameIdle, stopCloud, tickCloud } from "./Space";

type Pending = { callback: () => void; delay: number };

function setup() {
  const eventTarget = () => {
    const listeners = new Map<string, Set<() => void>>();
    return {
      target: {
        addEventListener: (type: string, listener: () => void) => {
          const values = listeners.get(type) ?? new Set();
          values.add(listener);
          listeners.set(type, values);
        },
        removeEventListener: (type: string, listener: () => void) => {
          listeners.get(type)?.delete(listener);
        },
      },
      emit: (type: string) => listeners.get(type)?.forEach((listener) => listener()),
    };
  };
  const canvasEvents = eventTarget();
  const controlEvents = eventTarget();
  const canvas = canvasEvents.target as unknown as HTMLCanvasElement;
  const controls = controlEvents.target;
  const pauseAnimation = vi.fn();
  const resumeAnimation = vi.fn();
  const pending = new Map<number, Pending>();
  let next = 1;
  const timer = {
    clear: (id: number) => pending.delete(id),
    set: (callback: () => void, delay: number) => {
      const id = next++;
      pending.set(id, { callback, delay });
      return id;
    },
  };
  const idle = makeFrameIdle(
    {
      controls: () => controls,
      pauseAnimation,
      renderer: () => ({ domElement: canvas }),
      resumeAnimation,
    },
    timer,
  );
  const flush = () => {
    const jobs = [...pending.values()];
    pending.clear();
    jobs.forEach(({ callback }) => callback());
  };
  return {
    canvas,
    controls,
    emitCanvas: canvasEvents.emit,
    emitControl: controlEvents.emit,
    idle,
    pauseAnimation,
    pending,
    resumeAnimation,
    flush,
  };
}

describe("3D idle frames", () => {
  it("uses motion density until the engine stops", () => {
    const cloud = { name: "archive-cloud" };
    const find = () => cloud;
    const graph = {
      scene: () => ({ getObjectByName: find }),
    };

    tickCloud(graph as never);
    tickCloud(graph as never);
    expect(cloudMocks.moveCloud).toHaveBeenCalledTimes(2);
    expect(cloudMocks.moveCloud).toHaveBeenLastCalledWith(cloud);
    expect(cloudMocks.restCloud).not.toHaveBeenCalled();

    stopCloud(graph as never);
    expect(cloudMocks.restCloud).toHaveBeenCalledOnce();
    expect(cloudMocks.restCloud).toHaveBeenCalledWith(cloud);
  });

  it("pauses only after the engine stops and the idle delay expires", () => {
    const run = setup();

    run.idle.engineTick();
    run.idle.touch();
    expect(run.pending.size).toBe(0);
    expect(run.pauseAnimation).not.toHaveBeenCalled();

    run.idle.engineStop(700 + FRAME_IDLE_WAIT);
    expect([...run.pending.values()][0]?.delay).toBe(700 + FRAME_IDLE_WAIT);
    expect(run.pauseAnimation).not.toHaveBeenCalled();
    run.flush();
    expect(run.pauseAnimation).toHaveBeenCalledOnce();
  });

  it("ignores blank motion but wakes for controls and release", () => {
    const run = setup();
    run.idle.engineStop();
    run.flush();

    run.emitCanvas("pointermove");
    run.emitCanvas("pointermove");
    expect(run.resumeAnimation).not.toHaveBeenCalled();
    expect(run.pending.size).toBe(0);

    run.emitControl("start");
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect(run.pending.size).toBe(0);
    run.emitControl("end");
    expect(run.pending.size).toBe(1);
    expect([...run.pending.values()][0]?.delay).toBe(FRAME_IDLE_WAIT);
    run.flush();
    expect(run.pauseAnimation).toHaveBeenCalledTimes(2);

    run.idle.dispose();
    run.emitCanvas("pointermove");
    run.emitControl("start");
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect(run.pending.size).toBe(0);
  });

  it("does not pause an active simulation after stale pointer activity", () => {
    const run = setup();
    run.idle.engineStop();
    run.emitCanvas("pointermove");
    expect(run.pending.size).toBe(1);

    run.idle.engineTick();
    expect(run.pending.size).toBe(0);
    run.flush();
    expect(run.pauseAnimation).not.toHaveBeenCalled();
  });
});
