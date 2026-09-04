import { beginAutoChange } from "./control";

export const FRAME_IDLE_WAIT = 240;
export const FRAME_ROTATE_WAIT = 2_500;
export const FRAME_HOVER_ROTATE_WAIT = 1_800;
export const FRAME_ROTATE_SPEED = 1;
export const FRAME_ROTATE_BUDGET = 18;
export const FRAME_ROTATE_SLOW_FRAME = 28;
export const FRAME_ROTATE_SLOW_LIMIT = 3;

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
  request: (callback: (time: number) => void) => number;
};

export type FrameIdle = {
  dispose: () => void;
  engineStop: (delay?: number) => void;
  engineTick: () => void;
  hover: (active: boolean) => void;
  motion: (reduced: boolean) => void;
  ready: (ready: boolean) => void;
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
  hoverPending: number;
  keys: Set<string>;
  paused: boolean;
  pending: number;
  pointers: Set<number>;
  probeFrame: number;
  ready: boolean;
  reducedMotion: boolean;
  rotateFrame: number;
  rotateLast: number;
  rotatePending: number;
  rotateSlow: number;
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

function primeRotation(
  timer: FrameTimer,
  state: IdleState,
  blocked: () => boolean,
  resume: () => void,
  pause: () => void,
): number | null {
  // Benchmark one stationary full-cloud frame before committing to a
  // continuous loop. Fast renderers get native requestAnimationFrame motion;
  // slow/software renderers stay still instead of producing visible pulses or
  // starving the input event queue.
  pause();
  const started = timer.now?.() ?? performance.now();
  resume();
  pause();
  if (blocked()) return null;
  return Math.max(0, (timer.now?.() ?? performance.now()) - started);
}

function watchRotation(
  controls: FrameControl,
  loop: FrameLoop,
  state: IdleState,
  blocked: () => boolean,
  stop: () => void,
) {
  const watch = (time: number) => {
    state.rotateFrame = 0;
    if (blocked() || !controls.autoRotate) return;
    if (state.rotateLast > 0) {
      state.rotateSlow =
        time - state.rotateLast > FRAME_ROTATE_SLOW_FRAME ? state.rotateSlow + 1 : 0;
      if (state.rotateSlow >= FRAME_ROTATE_SLOW_LIMIT) {
        stop();
        return;
      }
    }
    state.rotateLast = time;
    state.rotateFrame = loop.request(watch);
  };
  state.rotateFrame = loop.request(watch);
}

type IdleLifecycle = Pick<
  IdleCore,
  | "engineStop"
  | "engineTick"
  | "hover"
  | "motion"
  | "ready"
  | "start"
  | "touch"
  | "visibility"
  | "wake"
>;

function makeIdleLifecycle(
  state: IdleState,
  actions: Pick<
    IdleCore,
    "armRotate" | "cancel" | "pause" | "resume" | "stopRotate"
  > & { rest: (delay?: number) => void },
): IdleLifecycle {
  const { armRotate, cancel, pause, resume, rest, stopRotate } = actions;
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
  // Hover labels do not pin the scene. Pointer motion already opens a brief,
  // stable picking window; once the pointer rests, full-cloud rotation may
  // continue beneath it until an actual drag, wheel, key, or touch begins.
  const hover = () => undefined;
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
      if (state.running) cancel();
      else pause();
    } else {
      armRotate();
    }
  };
  const ready = (value: boolean) => {
    if (value === state.ready) return;
    state.ready = value;
    if (!value) {
      stopRotate();
      if (!state.running) pause();
      return;
    }
    armRotate();
  };
  const visibility = (hidden: boolean) => {
    state.hidden = hidden;
    if (hidden) {
      state.keys.clear();
      state.pointers.clear();
      state.controlActive = false;
      stopRotate();
      pause();
      return;
    }
    resume();
    rest();
    armRotate();
  };
  return {
    engineStop,
    engineTick,
    hover,
    motion,
    ready,
    start,
    touch,
    visibility,
    wake,
  };
}

function makeIdleCore(
  graph: FrameGraph,
  controls: FrameControl,
  timer: FrameTimer,
  loop: FrameLoop,
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
    if (state.rotateFrame) loop.cancel(state.rotateFrame);
    state.rotateFrame = 0;
    state.rotateLast = 0;
    state.rotateSlow = 0;
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
    !state.ready ||
    state.running ||
    state.controlActive ||
    state.keys.size > 0 ||
    state.pointers.size > 0;
  const beginRotate = () => {
    if (blocked()) return;
    // OrbitControls' internal timer otherwise includes the entire idle pause.
    // Render one stationary frame first to reset that delta, then enable
    // rotation on a native continuous animation loop. This avoids both a
    // catch-up jump and the visible stepping caused by timer-driven pulses.
    const cost = primeRotation(timer, state, blocked, resume, pause);
    if (cost === null || cost > FRAME_ROTATE_BUDGET) return;
    rotate(true);
    resume();
    watchRotation(controls, loop, state, blocked, () => {
      stopRotate();
      pause();
    });
  };
  const armRotate = () => {
    cancelRotate();
    if (!canRotate || blocked()) return;
    state.rotatePending = timer.set(() => {
      state.rotatePending = 0;
      beginRotate();
    }, FRAME_ROTATE_WAIT);
  };
  const lifecycle = makeIdleLifecycle(state, {
    armRotate,
    cancel,
    pause,
    resume,
    rest,
    stopRotate,
  });
  return {
    armRotate,
    beginRotate,
    cancel,
    pause,
    resume,
    stopRotate,
    ...lifecycle,
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
      core.stopRotate();
      state.hoverPending = timer.set(() => {
        state.hoverPending = 0;
        core.beginRotate();
      }, FRAME_HOVER_ROTATE_WAIT);
      core.pause();
      // Let ForceGraph process the pointer with one coalesced frame after the
      // continuous idle loop stops, then return to rest. Its foreground-node
      // raycaster otherwise retains the last automatic-rotation frame.
      draw();
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
    ready: false,
    rotateFrame: 0,
    rotateLast: 0,
    rotatePending: 0,
    rotateSlow: 0,
    running: true,
  };
  const core = makeIdleCore(graph, controls, timer, loop, state);
  const dispose = bindIdle(graph, controls, timer, loop, state, core);
  return {
    dispose,
    engineStop: core.engineStop,
    engineTick: core.engineTick,
    hover: core.hover,
    motion: core.motion,
    ready: core.ready,
    start: core.start,
    touch: core.touch,
    visibility: core.visibility,
    wake: core.wake,
  };
}
