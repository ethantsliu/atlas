import { beginAutoChange } from "./control";

export const FRAME_IDLE_WAIT = 240;
export const FRAME_ROTATE_WAIT = 5_000;
export const FRAME_HOVER_ROTATE_WAIT = 3_200;
export const FRAME_ROTATE_PACE = 16;
export const FRAME_ROTATE_SLOW_PACE = 240;
export const FRAME_ROTATE_SLOW_FRAME = 48;
export const FRAME_ROTATE_SPEED = 0.3;

export type FrameControl = {
  addEventListener?: (type: string, listener: (event: Event) => void) => void;
  atlasAutoEpoch?: number;
  autoRotate?: boolean;
  autoRotateSpeed?: number;
  removeEventListener?: (type: string, listener: (event: Event) => void) => void;
  zoomToCursor?: boolean;
};

export type FrameGraph = {
  controls: () => FrameControl;
  pauseAnimation: () => unknown;
  renderer: () => { domElement: HTMLCanvasElement };
  resumeAnimation: () => unknown;
};

type FrameTimer = {
  clear: (timer: number) => void;
  now?: () => number;
  set: (callback: () => void, delay: number) => number;
};

type FrameLoop = {
  cancel: (frame: number) => void;
  request: (callback: () => void) => number;
};

export type FrameIdle = {
  dispose: () => void;
  engineStop: (delay?: number) => void;
  engineTick: () => void;
  hover: (active: boolean) => void;
  motion: (reduced: boolean) => void;
  start: () => void;
  touch: () => void;
  visibility: (hidden: boolean) => void;
  wake: () => void;
};

export function enableCursorZoom(control: FrameControl | null | undefined): boolean {
  if (!control || !("zoomToCursor" in control)) return false;
  control.zoomToCursor = true;
  return true;
}

type IdleState = {
  controlActive: boolean;
  drawPending: number;
  hidden: boolean;
  hoverActive: boolean;
  hoverInterrupted: boolean;
  hoverPending: number;
  keys: Set<string>;
  paused: boolean;
  pending: number;
  pointers: Set<number>;
  probeFrame: number;
  reducedMotion: boolean;
  rotatePulse: number;
  rotatePending: number;
  running: boolean;
};

type IdleCore = Omit<FrameIdle, "dispose"> & {
  armRotate: () => void;
  beginRotate: () => void;
  cancel: () => void;
  pause: () => void;
  resume: () => void;
  stopRotate: () => void;
};

function pulseRotate(
  controls: FrameControl,
  timer: FrameTimer,
  state: IdleState,
  blocked: () => boolean,
  resume: () => void,
  pause: () => void,
) {
  const pulse = () => {
    state.rotatePulse = 0;
    if (blocked() || !controls.autoRotate) return;
    // ForceGraph renders once synchronously from resumeAnimation(), then
    // schedules its next frame. Cancel that next frame immediately and leave
    // an event-loop gap so a 3.15M-point draw cannot starve input/network work.
    const started = timer.now?.() ?? performance.now();
    resume();
    pause();
    if (blocked() || !controls.autoRotate) return;
    const elapsed = (timer.now?.() ?? performance.now()) - started;
    state.rotatePulse = timer.set(
      pulse,
      elapsed >= FRAME_ROTATE_SLOW_FRAME ? FRAME_ROTATE_SLOW_PACE : FRAME_ROTATE_PACE,
    );
  };
  pulse();
}

function makeIdleCore(
  graph: FrameGraph,
  controls: FrameControl,
  timer: FrameTimer,
  state: IdleState,
): IdleCore {
  const canRotate = "autoRotate" in controls;
  const cancel = () => {
    if (state.pending) timer.clear(state.pending);
    state.pending = 0;
  };
  const cancelRotate = () => {
    if (state.rotatePending) timer.clear(state.rotatePending);
    state.rotatePending = 0;
    if (state.hoverPending) timer.clear(state.hoverPending);
    state.hoverPending = 0;
    if (state.rotatePulse) timer.clear(state.rotatePulse);
    state.rotatePulse = 0;
  };
  const rotate = (active: boolean) => {
    if (!canRotate) return;
    if (active) beginAutoChange(controls);
    controls.autoRotate = active;
    if (active) controls.autoRotateSpeed = FRAME_ROTATE_SPEED;
  };
  const stopRotate = () => {
    cancelRotate();
    rotate(false);
  };
  const resume = () => {
    cancel();
    if (state.hidden || !state.paused) return;
    state.paused = false;
    graph.resumeAnimation();
  };
  const pause = () => {
    cancel();
    if (state.paused) return;
    state.paused = true;
    graph.pauseAnimation();
  };
  const rest = (delay = FRAME_IDLE_WAIT) => {
    cancel();
    if (state.hidden) {
      pause();
      return;
    }
    if (
      state.running ||
      state.controlActive ||
      state.keys.size > 0 ||
      state.pointers.size > 0 ||
      controls.autoRotate
    ) {
      return;
    }
    state.pending = timer.set(() => {
      state.pending = 0;
      pause();
    }, delay);
  };
  const blocked = () =>
    state.reducedMotion ||
    state.hidden ||
    state.running ||
    state.controlActive ||
    state.hoverActive ||
    state.keys.size > 0 ||
    state.pointers.size > 0;
  const beginRotate = () => {
    if (blocked()) return;
    rotate(true);
    pulseRotate(controls, timer, state, blocked, resume, pause);
  };
  const armRotate = () => {
    cancelRotate();
    if (!canRotate || blocked()) return;
    state.rotatePending = timer.set(() => {
      state.rotatePending = 0;
      beginRotate();
    }, FRAME_ROTATE_WAIT);
  };
  const start = () => {
    state.running = true;
    stopRotate();
    resume();
  };
  const wake = () => {
    resume();
    rest();
  };
  const touch = () => {
    stopRotate();
    wake();
    armRotate();
  };
  const hover = (active: boolean) => {
    if (active === state.hoverActive) return;
    state.hoverActive = active;
    if (active) {
      const interrupted = Boolean(
        controls.autoRotate || state.hoverPending || state.hoverInterrupted,
      );
      if (!interrupted) return;
      state.hoverInterrupted = true;
      stopRotate();
      pause();
      return;
    }
    // Preserve an untouched pre-rotation deadline. If that deadline elapsed
    // while metadata was busy, or this hover interrupted rotation, use the
    // shorter post-hover idle window.
    if (!state.hoverInterrupted && state.rotatePending) return;
    state.hoverInterrupted = false;
    if (!canRotate) return;
    if (state.hoverPending) timer.clear(state.hoverPending);
    state.hoverPending = timer.set(() => {
      state.hoverPending = 0;
      beginRotate();
    }, FRAME_HOVER_ROTATE_WAIT);
  };
  const engineTick = () => {
    state.running = true;
    stopRotate();
    cancel();
  };
  const engineStop = (delay = FRAME_IDLE_WAIT) => {
    state.running = false;
    rest(delay);
    armRotate();
  };
  const motion = (reduced: boolean) => {
    state.reducedMotion = reduced;
    if (reduced) {
      stopRotate();
      rest();
    } else {
      armRotate();
    }
  };
  const visibility = (hidden: boolean) => {
    state.hidden = hidden;
    if (hidden) {
      state.keys.clear();
      state.pointers.clear();
      state.controlActive = false;
      state.hoverActive = false;
      state.hoverInterrupted = false;
      stopRotate();
      pause();
      return;
    }
    resume();
    rest();
    armRotate();
  };
  return {
    armRotate,
    beginRotate,
    cancel,
    engineStop,
    engineTick,
    hover,
    motion,
    pause,
    resume,
    start,
    stopRotate,
    touch,
    visibility,
    wake,
  };
}

function bindIdle(
  graph: FrameGraph,
  controls: FrameControl,
  timer: FrameTimer,
  loop: FrameLoop,
  state: IdleState,
  core: IdleCore,
) {
  const canvas = graph.renderer().domElement;
  const pressTarget: EventTarget = canvas.ownerDocument ?? canvas;
  const releaseTarget: EventTarget = canvas.ownerDocument?.defaultView ?? canvas;
  const priorRotate = controls.autoRotate;
  const priorRotateSpeed = controls.autoRotateSpeed;
  const cancelDraw = () => {
    if (state.drawPending) timer.clear(state.drawPending);
    state.drawPending = 0;
  };
  const draw = () => {
    if (state.running || state.hidden || state.drawPending) return;
    state.drawPending = timer.set(() => {
      state.drawPending = 0;
      if (state.running || state.hidden) return;
      core.resume();
      core.pause();
    }, 0);
  };
  const stopInput = () => {
    cancelDraw();
    core.cancel();
    core.stopRotate();
  };
  const rearm = () => {
    core.stopRotate();
    if (!state.running) core.pause();
    core.armRotate();
  };
  const probe = () => {
    if (state.probeFrame) return;
    // Once rotating, passive hover opens a stable-camera picking window.
    const interrupted = Boolean(controls.autoRotate || state.hoverPending);
    if (interrupted) {
      state.hoverInterrupted = true;
      core.stopRotate();
      state.hoverPending = timer.set(() => {
        state.hoverPending = 0;
        core.beginRotate();
      }, FRAME_HOVER_ROTATE_WAIT);
      core.pause();
    } else {
      core.wake();
    }
    state.probeFrame = loop.request(() => {
      state.probeFrame = 0;
    });
  };
  const begin = () => {
    state.controlActive = true;
    stopInput();
  };
  const finish = () => {
    state.controlActive = false;
    if (state.pointers.size === 0) {
      draw();
      rearm();
    }
  };
  const press = (event: Event) => {
    state.pointers.add((event as PointerEvent).pointerId);
    stopInput();
  };
  const release = (event: Event) => {
    state.pointers.delete((event as PointerEvent).pointerId);
    if (state.pointers.size === 0 && !state.controlActive) rearm();
  };
  const keyName = (event: Event) => {
    const keyboard = event as KeyboardEvent;
    return keyboard.code || keyboard.key;
  };
  const keyPress = (event: Event) => {
    state.keys.add(keyName(event));
    stopInput();
  };
  const keyRelease = (event: Event) => {
    state.keys.delete(keyName(event));
    if (state.keys.size === 0 && state.pointers.size === 0 && !state.controlActive) {
      rearm();
    }
  };
  const focus = () => {
    if (state.running) {
      core.touch();
      return;
    }
    rearm();
  };
  const wheel = () => rearm();
  const change = () => {
    if (!controls.autoRotate) {
      core.stopRotate();
      draw();
    }
  };
  controls.addEventListener?.("start", begin);
  controls.addEventListener?.("change", change);
  controls.addEventListener?.("end", finish);
  canvas.addEventListener("pointermove", probe, true);
  pressTarget.addEventListener("pointerdown", press, true);
  pressTarget.addEventListener("focusin", focus, true);
  pressTarget.addEventListener("keydown", keyPress, true);
  releaseTarget.addEventListener("pointerup", release, true);
  releaseTarget.addEventListener("pointercancel", release, true);
  releaseTarget.addEventListener("keyup", keyRelease, true);
  canvas.addEventListener("wheel", wheel, true);
  return () => {
    cancelDraw();
    core.cancel();
    core.stopRotate();
    if ("autoRotate" in controls) controls.autoRotate = priorRotate;
    if ("autoRotate" in controls && priorRotateSpeed !== undefined) {
      controls.autoRotateSpeed = priorRotateSpeed;
    }
    if (state.probeFrame) loop.cancel(state.probeFrame);
    state.probeFrame = 0;
    controls.removeEventListener?.("start", begin);
    controls.removeEventListener?.("change", change);
    controls.removeEventListener?.("end", finish);
    canvas.removeEventListener("pointermove", probe, true);
    pressTarget.removeEventListener("pointerdown", press, true);
    pressTarget.removeEventListener("focusin", focus, true);
    pressTarget.removeEventListener("keydown", keyPress, true);
    releaseTarget.removeEventListener("pointerup", release, true);
    releaseTarget.removeEventListener("pointercancel", release, true);
    releaseTarget.removeEventListener("keyup", keyRelease, true);
    canvas.removeEventListener("wheel", wheel, true);
  };
}

export function makeFrameIdle(
  graph: FrameGraph,
  timer: FrameTimer = {
    clear: (value) => window.clearTimeout(value),
    set: (callback, delay) => window.setTimeout(callback, delay),
  },
  loop: FrameLoop = {
    cancel: (value) => window.cancelAnimationFrame(value),
    request: (callback) => window.requestAnimationFrame(callback),
  },
): FrameIdle {
  const controls = graph.controls();
  enableCursorZoom(controls);
  const state: IdleState = {
    controlActive: false,
    drawPending: 0,
    hidden: false,
    hoverPending: 0,
    keys: new Set(),
    paused: false,
    pending: 0,
    pointers: new Set(),
    probeFrame: 0,
    reducedMotion: false,
    rotatePending: 0,
    running: true,
    hoverActive: false,
    hoverInterrupted: false,
    rotatePulse: 0,
  };
  const core = makeIdleCore(graph, controls, timer, state);
  const dispose = bindIdle(graph, controls, timer, loop, state, core);
  return {
    dispose,
    engineStop: core.engineStop,
    engineTick: core.engineTick,
    hover: core.hover,
    motion: core.motion,
    start: core.start,
    touch: core.touch,
    visibility: core.visibility,
    wake: core.wake,
  };
}
