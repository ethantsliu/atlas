import { beginAutoChange } from "./control";

export const FRAME_IDLE_WAIT = 240;
export const FRAME_ROTATE_WAIT = 3_000;
export const FRAME_ROTATE_SPEED = 0;
export const FRAME_YAW_RATE = 0.22;
export const FRAME_TILT_RATE = 0.068;
export const FRAME_TILT_FREQUENCY = 0.4;

type FramePoint = { x: number; y: number; z: number };

export type FrameControl = {
  addEventListener?: (type: string, listener: (event: Event) => void) => void;
  atlasAutoEpoch?: number;
  autoRotate?: boolean;
  autoRotateSpeed?: number;
  object?: { lookAt?: (target: FramePoint) => void; position: FramePoint };
  removeEventListener?: (type: string, listener: (event: Event) => void) => void;
  target?: FramePoint;
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
  everReady: boolean;
  hidden: boolean;
  hiddenAt: number | null;
  keys: Set<string>;
  paused: boolean;
  pending: number;
  pointerChanged: boolean;
  pointerOrigins: Map<number, FramePoint>;
  pointerRotating: boolean;
  pointers: Set<number>;
  probeFrame: number;
  ready: boolean;
  reducedMotion: boolean;
  rotateFrame: number;
  rotateElapsed: number;
  rotateLast: number;
  rotatePending: number;
  rotating: boolean;
  running: boolean;
  resumeRotation: boolean;
};

type IdleCore = Omit<FrameIdle, "dispose"> & {
  armRotate: () => void;
  beginRotate: () => void;
  cancel: () => void;
  pause: () => void;
  resume: () => void;
  stopRotate: () => void;
};

export function orbitControl(
  controls: FrameControl,
  yawAngle: number,
  pitchAngle: number,
): boolean {
  const position = controls.object?.position;
  const target = controls.target;
  if (
    !position ||
    !target ||
    !Number.isFinite(yawAngle) ||
    !Number.isFinite(pitchAngle)
  ) {
    return false;
  }
  const dx = position.x - target.x;
  const dy = position.y - target.y;
  const dz = position.z - target.z;
  const radius = Math.hypot(dx, dy, dz);
  if (!Number.isFinite(radius) || radius < 0.01) return false;
  const polar = Math.acos(Math.max(-1, Math.min(1, dy / radius)));
  const next = Math.max(0.15, Math.min(Math.PI - 0.15, polar - pitchAngle));
  const level = Math.sin(next) * radius;
  const yaw = Math.atan2(dx, dz) + yawAngle;
  position.x = target.x + Math.sin(yaw) * level;
  position.y = target.y + Math.cos(next) * radius;
  position.z = target.z + Math.cos(yaw) * level;
  controls.object?.lookAt?.(target);
  return true;
}

export function tiltControl(controls: FrameControl, angle: number): boolean {
  return orbitControl(controls, 0, angle);
}

export function advanceRotation(
  controls: FrameControl,
  seconds: number,
  elapsed: number,
): number {
  if (!Number.isFinite(seconds) || seconds <= 0) return elapsed;
  const next = elapsed + seconds;
  const pitch =
    (Math.sin(next * FRAME_TILT_FREQUENCY) - Math.sin(elapsed * FRAME_TILT_FREQUENCY)) *
    (FRAME_TILT_RATE / FRAME_TILT_FREQUENCY);
  orbitControl(controls, (-FRAME_YAW_RATE * seconds) % (Math.PI * 2), pitch);
  return next;
}

function watchRotation(
  controls: FrameControl,
  loop: FrameLoop,
  state: IdleState,
  blocked: () => boolean,
) {
  const watch = (time: number) => {
    state.rotateFrame = 0;
    if (blocked() || !controls.autoRotate) return;
    if (state.rotateLast > 0) {
      const seconds = Math.min(0.1, (time - state.rotateLast) / 1_000);
      state.rotateElapsed = advanceRotation(controls, seconds, state.rotateElapsed);
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
    "armRotate" | "beginRotate" | "cancel" | "pause" | "resume" | "stopRotate"
  > & {
    catchUp: () => void;
    now: () => number;
    rest: (delay?: number) => void;
  },
): IdleLifecycle {
  const { armRotate, beginRotate, cancel, pause, resume, rest, stopRotate } = actions;
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
  const hover = (_active: boolean) => undefined;
  const engineTick = () => {
    state.running = true;
    cancel();
  };
  const engineStop = (delay = FRAME_IDLE_WAIT) => {
    state.running = false;
    if (state.rotating) return;
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
    const firstReady = value && !state.everReady;
    state.ready = value;
    if (value) state.everReady = true;
    if (!value) {
      stopRotate();
      if (!state.running) pause();
      return;
    }
    if (firstReady && state.hidden && !state.reducedMotion) {
      state.resumeRotation = true;
      state.hiddenAt ??= actions.now();
      return;
    }
    if (firstReady) beginRotate();
    else armRotate();
  };
  const visibility = (hidden: boolean) => {
    state.hidden = hidden;
    if (hidden) {
      state.resumeRotation = state.rotating;
      state.hiddenAt = state.resumeRotation ? actions.now() : null;
      state.keys.clear();
      state.pointers.clear();
      state.pointerChanged = false;
      state.pointerOrigins.clear();
      state.pointerRotating = false;
      state.controlActive = false;
      stopRotate();
      pause();
      return;
    }
    resume();
    rest();
    if (state.resumeRotation) {
      state.resumeRotation = false;
      actions.catchUp();
      beginRotate();
    } else {
      armRotate();
    }
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
  const canvas = graph.renderer().domElement;
  const now = () => timer.now?.() ?? Date.now();
  const cancel = () => {
    if (state.pending) timer.clear(state.pending);
    state.pending = 0;
  };
  const cancelRotate = () => {
    if (state.rotatePending) timer.clear(state.rotatePending);
    state.rotatePending = 0;
    if (state.rotateFrame) loop.cancel(state.rotateFrame);
    state.rotateFrame = 0;
    state.rotateLast = 0;
    if (canvas.dataset) delete canvas.dataset.autoRotateAt;
  };
  const catchUp = () => {
    if (state.hiddenAt == null) return;
    const seconds = Math.max(0, (now() - state.hiddenAt) / 1_000);
    state.hiddenAt = null;
    state.rotateElapsed = advanceRotation(controls, seconds, state.rotateElapsed);
  };
  const rotate = (active: boolean) => {
    if (!canRotate) return;
    if (active) beginAutoChange(controls);
    state.rotating = active;
    controls.autoRotate = active;
    if (active) controls.autoRotateSpeed = FRAME_ROTATE_SPEED;
    if (canvas.dataset) canvas.dataset.autoRotate = String(active);
    if (active && canvas.dataset) delete canvas.dataset.autoRotateAt;
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
    state.controlActive ||
    state.keys.size > 0 ||
    state.pointers.size > 0;
  const beginRotate = () => {
    if (!canRotate || blocked()) return;
    rotate(true);
    resume();
    watchRotation(controls, loop, state, blocked);
  };
  const armRotate = () => {
    if (state.rotatePending || state.rotating) return;
    cancelRotate();
    if (!canRotate || blocked()) return;
    if (canvas.dataset) {
      canvas.dataset.autoRotateAt = String(Date.now() + FRAME_ROTATE_WAIT);
    }
    state.rotatePending = timer.set(() => {
      state.rotatePending = 0;
      beginRotate();
    }, FRAME_ROTATE_WAIT);
  };
  const lifecycle = makeIdleLifecycle(state, {
    armRotate,
    beginRotate,
    cancel,
    catchUp,
    now,
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
    if (!controls.autoRotate) core.wake();
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
      if (state.pointerRotating && !state.pointerChanged) core.beginRotate();
      else rearm();
      state.pointerRotating = false;
    }
  };
  const press = (event: Event) => {
    const pointer = event as PointerEvent;
    if (state.pointers.size === 0) {
      state.pointerChanged = false;
      state.pointerRotating = Boolean(controls.autoRotate);
    }
    state.pointers.add(pointer.pointerId);
    state.pointerOrigins.set(pointer.pointerId, {
      x: pointer.clientX,
      y: pointer.clientY,
      z: 0,
    });
    stopInput();
  };
  const drag = (event: Event) => {
    const pointer = event as PointerEvent;
    const origin = state.pointerOrigins.get(pointer.pointerId);
    if (
      origin &&
      Math.hypot(pointer.clientX - origin.x, pointer.clientY - origin.y) > 5
    ) {
      state.pointerChanged = true;
    }
  };
  const release = (event: Event) => {
    const pointer = event as PointerEvent;
    state.pointers.delete(pointer.pointerId);
    state.pointerOrigins.delete(pointer.pointerId);
    if (state.pointers.size !== 0 || state.controlActive) return;
    if (state.pointerRotating && !state.pointerChanged) core.beginRotate();
    else rearm();
    state.pointerRotating = false;
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
  const wheel = () => rearm();
  const change = () => {
    if (!controls.autoRotate) {
      core.stopRotate();
      draw();
      core.armRotate();
    }
  };
  controls.addEventListener?.("start", begin);
  controls.addEventListener?.("change", change);
  controls.addEventListener?.("end", finish);
  canvas.addEventListener("pointermove", probe, true);
  pressTarget.addEventListener("pointerdown", press, true);
  pressTarget.addEventListener("pointermove", drag, true);
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
    pressTarget.removeEventListener("pointermove", drag, true);
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
    everReady: false,
    hidden: false,
    hiddenAt: null,
    keys: new Set(),
    paused: false,
    pending: 0,
    pointerChanged: false,
    pointerOrigins: new Map(),
    pointerRotating: false,
    pointers: new Set(),
    probeFrame: 0,
    reducedMotion: false,
    ready: false,
    rotateFrame: 0,
    rotateElapsed: 0,
    rotateLast: 0,
    rotatePending: 0,
    rotating: false,
    running: true,
    resumeRotation: false,
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
