import { beginAutoChange } from "./control";

export const FRAME_IDLE_WAIT = 240;
export const FRAME_ROTATE_WAIT = 5_000;
export const FRAME_HOVER_ROTATE_WAIT = 3_200;
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
  const canvas = graph.renderer().domElement;
  const controls = graph.controls();
  const pressTarget: EventTarget = canvas.ownerDocument ?? canvas;
  const releaseTarget: EventTarget = canvas.ownerDocument?.defaultView ?? canvas;
  enableCursorZoom(controls);
  let running = true;
  let paused = false;
  let pending = 0;
  let rotatePending = 0;
  let hoverPending = 0;
  let probeFrame = 0;
  let reducedMotion = false;
  let hidden = false;
  let controlActive = false;
  const keys = new Set<string>();
  const pointers = new Set<number>();
  // OrbitControls exposes a supported idle-rotation switch. The narrow mobile
  // layout intentionally retains TrackballControls because its two-finger
  // gestures are more reliable, and TrackballControls has no auto-rotate API.
  const canRotate = "autoRotate" in controls;
  const priorRotate = controls.autoRotate;
  const priorRotateSpeed = controls.autoRotateSpeed;
  const cancel = () => {
    if (pending) timer.clear(pending);
    pending = 0;
  };
  const cancelRotate = () => {
    if (rotatePending) timer.clear(rotatePending);
    rotatePending = 0;
    if (hoverPending) timer.clear(hoverPending);
    hoverPending = 0;
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
    if (hidden || !paused) return;
    paused = false;
    graph.resumeAnimation();
  };
  const pause = () => {
    cancel();
    if (paused) return;
    paused = true;
    graph.pauseAnimation();
  };
  const rest = (delay = FRAME_IDLE_WAIT) => {
    cancel();
    if (hidden) {
      pause();
      return;
    }
    if (
      running ||
      controlActive ||
      keys.size > 0 ||
      pointers.size > 0 ||
      controls.autoRotate
    ) {
      return;
    }
    pending = timer.set(() => {
      pending = 0;
      pause();
    }, delay);
  };
  const blocked = () =>
    reducedMotion ||
    hidden ||
    running ||
    controlActive ||
    keys.size > 0 ||
    pointers.size > 0;
  const beginRotate = () => {
    if (blocked()) return;
    rotate(true);
    resume();
  };
  const armRotate = () => {
    cancelRotate();
    if (!canRotate || blocked()) return;
    rotatePending = timer.set(() => {
      rotatePending = 0;
      beginRotate();
    }, FRAME_ROTATE_WAIT);
  };
  const start = () => {
    running = true;
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
  const probe = () => {
    if (probeFrame) return;
    // Before rotation, passive hover leaves the original five-second idle
    // deadline untouched. Once rotating, it opens a shorter stable-camera
    // window so the full-cloud GPU picker and tooltip can settle.
    if (controls.autoRotate || hoverPending) {
      if (hoverPending) timer.clear(hoverPending);
      hoverPending = 0;
      rotate(false);
      hoverPending = timer.set(() => {
        hoverPending = 0;
        beginRotate();
      }, FRAME_HOVER_ROTATE_WAIT);
    }
    wake();
    probeFrame = loop.request(() => {
      probeFrame = 0;
    });
  };
  const engineTick = () => {
    running = true;
    stopRotate();
    cancel();
  };
  const engineStop = (delay = FRAME_IDLE_WAIT) => {
    running = false;
    rest(delay);
    armRotate();
  };
  const begin = () => {
    controlActive = true;
    stopRotate();
    resume();
  };
  const finish = () => {
    controlActive = false;
    if (pointers.size > 0) return;
    touch();
  };
  const press = (event: Event) => {
    pointers.add((event as PointerEvent).pointerId);
    stopRotate();
    resume();
  };
  const release = (event: Event) => {
    pointers.delete((event as PointerEvent).pointerId);
    if (pointers.size > 0 || controlActive) return;
    touch();
  };
  const keyName = (event: Event) => {
    const keyboard = event as KeyboardEvent;
    return keyboard.code || keyboard.key;
  };
  const keyPress = (event: Event) => {
    keys.add(keyName(event));
    stopRotate();
    resume();
  };
  const keyRelease = (event: Event) => {
    keys.delete(keyName(event));
    if (keys.size > 0 || pointers.size > 0 || controlActive) return;
    touch();
  };
  const wheel = () => touch();
  const change = () => {
    if (!controls.autoRotate) touch();
  };
  controls.addEventListener?.("start", begin);
  controls.addEventListener?.("change", change);
  controls.addEventListener?.("end", finish);
  canvas.addEventListener("pointermove", probe, true);
  pressTarget.addEventListener("pointerdown", press, true);
  pressTarget.addEventListener("keydown", keyPress, true);
  releaseTarget.addEventListener("pointerup", release, true);
  releaseTarget.addEventListener("pointercancel", release, true);
  releaseTarget.addEventListener("keyup", keyRelease, true);
  canvas.addEventListener("wheel", wheel, true);

  return {
    dispose: () => {
      cancel();
      stopRotate();
      if (canRotate) controls.autoRotate = priorRotate;
      if (canRotate && priorRotateSpeed !== undefined) {
        controls.autoRotateSpeed = priorRotateSpeed;
      }
      if (probeFrame) loop.cancel(probeFrame);
      probeFrame = 0;
      controls.removeEventListener?.("start", begin);
      controls.removeEventListener?.("change", change);
      controls.removeEventListener?.("end", finish);
      canvas.removeEventListener("pointermove", probe, true);
      pressTarget.removeEventListener("pointerdown", press, true);
      pressTarget.removeEventListener("keydown", keyPress, true);
      releaseTarget.removeEventListener("pointerup", release, true);
      releaseTarget.removeEventListener("pointercancel", release, true);
      releaseTarget.removeEventListener("keyup", keyRelease, true);
      canvas.removeEventListener("wheel", wheel, true);
    },
    engineStop,
    engineTick,
    motion: (reduced) => {
      reducedMotion = reduced;
      if (reduced) {
        stopRotate();
        rest();
      } else {
        armRotate();
      }
    },
    start,
    touch,
    visibility: (nextHidden) => {
      hidden = nextHidden;
      if (hidden) {
        keys.clear();
        pointers.clear();
        controlActive = false;
        stopRotate();
        pause();
        return;
      }
      resume();
      rest();
      armRotate();
    },
    wake,
  };
}
