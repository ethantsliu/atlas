import { describe, expect, it, vi } from "vitest";

vi.mock("react-force-graph-3d", () => ({ default: () => null }));

import { cameraControl } from "./Space";
import {
  FRAME_HOVER_ROTATE_WAIT,
  FRAME_IDLE_WAIT,
  FRAME_ROTATE_BUDGET,
  FRAME_ROTATE_SLOW_FRAME,
  FRAME_ROTATE_SLOW_LIMIT,
  FRAME_ROTATE_SPEED,
  FRAME_ROTATE_WAIT,
  enableCursorZoom,
  makeFrameIdle,
} from "../../hooks/idle";

type Pending = { callback: () => void; delay: number };

function setup(rotate = false, frameTime = 0, frameInterval = 16, ready = true) {
  const eventTarget = () => {
    const listeners = new Map<string, Set<(event: Event) => void>>();
    return {
      target: {
        addEventListener: (type: string, listener: (event: Event) => void) => {
          const values = listeners.get(type) ?? new Set();
          values.add(listener);
          listeners.set(type, values);
        },
        removeEventListener: (type: string, listener: (event: Event) => void) => {
          listeners.get(type)?.delete(listener);
        },
      },
      emit: (type: string, event = new Event(type)) =>
        listeners.get(type)?.forEach((listener) => listener(event)),
    };
  };
  const canvasEvents = eventTarget();
  const controlEvents = eventTarget();
  const documentEvents = eventTarget();
  const windowEvents = eventTarget();
  Object.assign(documentEvents.target, { defaultView: windowEvents.target });
  Object.assign(canvasEvents.target, { ownerDocument: documentEvents.target });
  const canvas = canvasEvents.target as unknown as HTMLCanvasElement;
  const controls = Object.assign(
    controlEvents.target,
    rotate ? { autoRotate: false, autoRotateSpeed: 2 } : {},
  );
  let now = 0;
  const resumeRotations: boolean[] = [];
  const pauseAnimation = vi.fn();
  const resumeAnimation = vi.fn(() => {
    resumeRotations.push(Boolean(controls.autoRotate));
    now += frameTime;
  });
  const pending = new Map<number, Pending>();
  const frames = new Map<number, (time: number) => void>();
  let frameNow = 0;
  let next = 1;
  const timer = {
    clear: (id: number) => pending.delete(id),
    now: () => now,
    set: (callback: () => void, delay: number) => {
      const id = next++;
      pending.set(id, { callback, delay });
      return id;
    },
  };
  const loop = {
    cancel: (id: number) => frames.delete(id),
    request: (callback: (time: number) => void) => {
      const id = next++;
      frames.set(id, callback);
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
    loop,
  );
  idle.ready(ready);
  const flush = () => {
    const jobs = [...pending.values()];
    pending.clear();
    jobs.forEach(({ callback }) => callback());
  };
  const flushFrames = () => {
    const jobs = [...frames.values()];
    frames.clear();
    frameNow += frameInterval;
    jobs.forEach((callback) => callback(frameNow));
  };
  const flushDelay = (delay: number) => {
    const jobs = [...pending].filter(([, job]) => job.delay === delay);
    jobs.forEach(([id, { callback }]) => {
      pending.delete(id);
      callback();
    });
  };
  const pointer = (type: string, id: number) => {
    const event = new Event(type);
    Object.defineProperty(event, "pointerId", { value: id });
    if (type === "pointerdown") documentEvents.emit(type, event);
    else windowEvents.emit(type, event);
  };
  const key = (type: string, value: string) => {
    const event = new Event(type);
    Object.defineProperties(event, {
      code: { value },
      key: { value },
    });
    if (type === "keydown") documentEvents.emit(type, event);
    else windowEvents.emit(type, event);
  };
  const focus = () => documentEvents.emit("focusin");
  return {
    canvas,
    controls,
    emitCanvas: canvasEvents.emit,
    emitControl: controlEvents.emit,
    idle,
    pauseAnimation,
    pending,
    resumeAnimation,
    resumeRotations,
    flush,
    flushDelay,
    flushFrames,
    frames,
    focus,
    key,
    pointer,
  };
}

describe("3D idle frames", () => {
  it("uses roll-free orbit controls for pointers and proven touch controls on mobile", () => {
    expect(cameraControl(1_440)).toBe("orbit");
    expect(cameraControl(688)).toBe("orbit");
    expect(cameraControl(521)).toBe("orbit");
    expect(cameraControl(520)).toBe("trackball");
    expect(cameraControl(390)).toBe("trackball");
  });

  it("enables native cursor zoom only when the control supports it", () => {
    const orbit = { zoomToCursor: false };
    const trackball = {};

    expect(enableCursorZoom(orbit)).toBe(true);
    expect(enableCursorZoom(trackball)).toBe(false);

    expect(orbit.zoomToCursor).toBe(true);
    expect(trackball).not.toHaveProperty("zoomToCursor");
  });

  it("pauses only after the engine stops and the idle delay expires", () => {
    const run = setup();

    run.idle.engineTick();
    run.focus();
    expect(run.pending.size).toBe(0);
    expect(run.pauseAnimation).not.toHaveBeenCalled();

    run.idle.engineStop(700 + FRAME_IDLE_WAIT);
    expect([...run.pending.values()][0]?.delay).toBe(700 + FRAME_IDLE_WAIT);
    expect(run.pauseAnimation).not.toHaveBeenCalled();
    run.flush();
    expect(run.pauseAnimation).toHaveBeenCalledOnce();
  });

  it("wakes for pointer probes, controls, and release", () => {
    const run = setup();
    run.idle.engineStop();
    run.flush();

    run.emitCanvas("pointermove");
    run.emitCanvas("pointermove");
    expect(run.frames.size).toBe(1);
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect(run.pending.size).toBe(1);
    run.flushFrames();
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect(run.pending.size).toBe(1);

    run.emitControl("start");
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect(run.pending.size).toBe(0);
    run.emitControl("change");
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([0]);
    run.emitControl("end");
    expect(run.pending.size).toBe(1);
    expect([...run.pending.values()][0]?.delay).toBe(0);
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    run.flush();
    expect(run.resumeAnimation).toHaveBeenCalledTimes(2);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);

    run.idle.dispose();
    run.emitCanvas("pointermove");
    run.emitControl("start");
    run.focus();
    expect(run.resumeAnimation).toHaveBeenCalledTimes(2);
    expect(run.pending.size).toBe(0);
    expect(run.frames.size).toBe(0);
  });

  it("does not pause an active simulation after stale pointer activity", () => {
    const run = setup();
    run.idle.engineStop();
    run.emitCanvas("pointermove");
    expect(run.pending.size).toBe(1);

    run.idle.engineTick();
    expect(run.pending.size).toBe(0);
    run.flushFrames();
    run.flush();
    expect(run.pauseAnimation).not.toHaveBeenCalled();
  });

  it("cancels a queued pointer probe on disposal", () => {
    const run = setup();

    run.emitCanvas("pointermove");
    expect(run.frames.size).toBe(1);
    run.idle.dispose();
    expect(run.frames.size).toBe(0);
    run.flushFrames();
    expect(run.resumeAnimation).not.toHaveBeenCalled();
  });

  it("starts subtle rotation after genuine idle time", () => {
    const run = setup(true);

    run.idle.engineStop();
    expect([...run.pending.values()].map(({ delay }) => delay).sort()).toEqual([
      FRAME_IDLE_WAIT,
      FRAME_ROTATE_WAIT,
    ]);
    run.flushDelay(FRAME_IDLE_WAIT);
    expect(run.pauseAnimation).toHaveBeenCalledOnce();
    expect(run.controls.autoRotate).toBe(false);

    const rotationTimer = [...run.pending].find(
      ([, { delay }]) => delay === FRAME_ROTATE_WAIT,
    )?.[0];
    run.emitCanvas("pointermove");
    expect(
      [...run.pending].find(([, { delay }]) => delay === FRAME_ROTATE_WAIT)?.[0],
    ).toBe(rotationTimer);
    run.flushFrames();

    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);
    expect(run.controls.autoRotateSpeed).toBe(FRAME_ROTATE_SPEED);
    expect(run.resumeAnimation).toHaveBeenCalledTimes(3);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);
    expect(run.resumeRotations.slice(-2)).toEqual([false, true]);
    expect(run.pending.size).toBe(0);
  });

  it("keeps a slow full-cloud renderer static instead of pulsing", () => {
    const run = setup(true, FRAME_ROTATE_BUDGET + 1);
    run.idle.engineStop();
    run.flushDelay(FRAME_IDLE_WAIT);
    run.flushDelay(FRAME_ROTATE_WAIT);

    expect(run.controls.autoRotate).toBe(false);
    expect(run.resumeAnimation).toHaveBeenCalledOnce();
    expect(run.resumeRotations).toEqual([false]);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(2);
    expect(run.pending.size).toBe(0);
  });

  it("stops continuous rotation after sustained slow animation frames", () => {
    const run = setup(true, 0, FRAME_ROTATE_SLOW_FRAME + 1);
    run.idle.engineStop();
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    for (let frame = 0; frame <= FRAME_ROTATE_SLOW_LIMIT; frame += 1) {
      run.flushFrames();
    }

    expect(run.controls.autoRotate).toBe(false);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);
    expect(run.frames.size).toBe(0);
    expect(run.pending.size).toBe(0);
  });

  it("does not arm rotation until the complete cloud and view are ready", () => {
    const run = setup(true, 0, 16, false);
    run.idle.engineStop();
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_IDLE_WAIT,
    ]);

    run.idle.ready(true);
    expect([...run.pending.values()].map(({ delay }) => delay).sort()).toEqual([
      FRAME_IDLE_WAIT,
      FRAME_ROTATE_WAIT,
    ]);
  });

  it("stops and pauses continuous rotation when readiness is lost", () => {
    const run = setup(true);
    run.idle.engineStop();
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    run.idle.ready(false);

    expect(run.controls.autoRotate).toBe(false);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);
    expect(run.frames.size).toBe(0);
    expect(run.pending.size).toBe(0);
  });

  it("stops on pointer activity and wheel then waits before resuming", () => {
    const run = setup(true);
    run.idle.engineStop();
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    const pointerResumes = run.resumeAnimation.mock.calls.length;
    run.pointer("pointerdown", 7);
    run.emitControl("start");
    expect(run.controls.autoRotate).toBe(false);
    expect(run.resumeAnimation).toHaveBeenCalledTimes(pointerResumes);
    expect(run.pending.size).toBe(0);
    run.emitControl("end");
    expect(run.pending.size).toBe(0);
    run.pointer("pointerup", 7);
    expect(run.resumeAnimation).toHaveBeenCalledTimes(pointerResumes);
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_ROTATE_WAIT,
    ]);

    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);
    const wheelResumes = run.resumeAnimation.mock.calls.length;
    run.emitCanvas("wheel");
    expect(run.controls.autoRotate).toBe(false);
    expect(run.resumeAnimation).toHaveBeenCalledTimes(wheelResumes);
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_ROTATE_WAIT,
    ]);

    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);
    run.emitCanvas("pointermove");
    run.flushFrames();
    expect(run.controls.autoRotate).toBe(false);
    expect([...run.pending.values()].map(({ delay }) => delay).sort()).toEqual([
      0,
      FRAME_HOVER_ROTATE_WAIT,
    ]);
    run.idle.hover(true);
    expect([...run.pending.values()].map(({ delay }) => delay).sort()).toEqual([
      0,
      FRAME_HOVER_ROTATE_WAIT,
    ]);
    expect(run.controls.autoRotate).toBe(false);
    run.flushDelay(0);
    run.flushDelay(FRAME_HOVER_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    run.idle.hover(false);
    expect(run.controls.autoRotate).toBe(true);
    expect(run.pending.size).toBe(0);
  });

  it("stops on keyboard focus, holds through activation, and re-arms", () => {
    const run = setup(true);
    run.idle.engineStop();
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    run.focus();
    expect(run.controls.autoRotate).toBe(false);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_ROTATE_WAIT,
    ]);
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    const keyResumes = run.resumeAnimation.mock.calls.length;
    run.key("keydown", "Enter");
    expect(run.controls.autoRotate).toBe(false);
    expect(run.resumeAnimation).toHaveBeenCalledTimes(keyResumes);
    expect(run.pending.size).toBe(0);
    run.key("keyup", "Enter");
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_ROTATE_WAIT,
    ]);
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    run.key("keydown", "Space");
    expect(run.controls.autoRotate).toBe(false);
    run.key("keyup", "Space");
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_ROTATE_WAIT,
    ]);
  });

  it("keeps the mobile trackball idle instead of emulating unsupported rotation", () => {
    const run = setup(false);
    run.idle.engineStop();

    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_IDLE_WAIT,
    ]);
    run.flushDelay(FRAME_IDLE_WAIT);
    expect(run.pauseAnimation).toHaveBeenCalledOnce();
    expect(run.controls).not.toHaveProperty("autoRotate");
  });

  it("honors reduced motion dynamically and restores control settings", () => {
    const run = setup(true);
    run.idle.engineStop();
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    run.idle.motion(true);
    expect(run.controls.autoRotate).toBe(false);
    expect(run.pending.size).toBe(0);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);

    run.idle.motion(false);
    expect([...run.pending.values()].map(({ delay }) => delay)).toEqual([
      FRAME_ROTATE_WAIT,
    ]);
    run.idle.dispose();
    expect(run.controls.autoRotate).toBe(false);
    expect(run.controls.autoRotateSpeed).toBe(2);
    expect(run.pending.size).toBe(0);
  });

  it("disables rendering while hidden and re-arms only after visibility returns", () => {
    const run = setup(true);
    run.idle.engineStop();
    run.flushDelay(FRAME_ROTATE_WAIT);
    expect(run.controls.autoRotate).toBe(true);

    run.idle.visibility(true);
    expect(run.controls.autoRotate).toBe(false);
    expect(run.pauseAnimation).toHaveBeenCalledTimes(3);
    expect(run.pending.size).toBe(0);

    run.idle.visibility(false);
    expect(run.resumeAnimation).toHaveBeenCalledTimes(3);
    expect([...run.pending.values()].map(({ delay }) => delay).sort()).toEqual([
      FRAME_IDLE_WAIT,
      FRAME_ROTATE_WAIT,
    ]);
  });
});
