import { RotateCcw } from "lucide-react";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  type FocusEvent,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { usePanel } from "../../hooks/panel";

type DragState = {
  pointer: number;
  startX: number;
  startWidth: number;
  startPreferred: number;
  latest: number;
};

function clampWidth(width: number, min: number, max: number) {
  return Math.min(max, Math.max(min, Math.round(width)));
}

export function PanelResize() {
  const { width, preferred, min, max, resize, restore, commit, reset } = usePanel();
  const rootRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const frameRef = useRef<number>();
  const focusRef = useRef(false);

  function focusInspector() {
    document.getElementById("map-inspector")?.focus({ preventScroll: true });
  }

  function blurPanel(event: FocusEvent<HTMLDivElement>) {
    if (event.currentTarget.contains(event.relatedTarget)) return;
    window.requestAnimationFrame(() => {
      if (window.matchMedia("(max-width: 1100px)").matches) focusInspector();
      focusRef.current = false;
    });
  }

  function flushResize() {
    if (!dragRef.current) return;
    resize(dragRef.current.latest);
    frameRef.current = undefined;
  }

  function startResize(event: PointerEvent<HTMLDivElement>) {
    if (!event.isPrimary || event.button !== 0) return;
    event.preventDefault();
    dragRef.current = {
      pointer: event.pointerId,
      startX: event.clientX,
      startWidth: width,
      startPreferred: preferred,
      latest: width,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveResize(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointer !== event.pointerId) return;
    drag.latest = clampWidth(drag.startWidth + drag.startX - event.clientX, min, max);
    if (frameRef.current == null) {
      frameRef.current = window.requestAnimationFrame(flushResize);
    }
  }

  function stopResize(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointer !== event.pointerId) return;
    window.cancelAnimationFrame(frameRef.current ?? 0);
    frameRef.current = undefined;
    resize(drag.latest);
    commit(drag.latest);
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function cancelResize(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointer !== event.pointerId) return;
    window.cancelAnimationFrame(frameRef.current ?? 0);
    frameRef.current = undefined;
    restore(drag.startPreferred);
    dragRef.current = null;
  }

  function keyResize(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 48 : 16;
    let next: number | null = null;
    if (event.key === "ArrowLeft") next = width + step;
    if (event.key === "ArrowRight") next = width - step;
    if (event.key === "Home") next = min;
    if (event.key === "End") next = max;
    if (event.key === "Enter") {
      event.preventDefault();
      reset();
      return;
    }
    if (next == null) return;
    event.preventDefault();
    commit(clampWidth(next, min, max));
  }

  useLayoutEffect(() => {
    const layout = rootRef.current?.parentElement;
    layout?.style.setProperty("--panel-width", `${width}px`);
    return () => {
      layout?.style.removeProperty("--panel-width");
    };
  }, [width]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1100px)");
    function handleStacked() {
      if (!media.matches) return;
      const drag = dragRef.current;
      if (drag) {
        window.cancelAnimationFrame(frameRef.current ?? 0);
        frameRef.current = undefined;
        restore(drag.startPreferred);
        dragRef.current = null;
      }
      if (focusRef.current || rootRef.current?.contains(document.activeElement)) {
        focusInspector();
      }
    }
    media.addEventListener("change", handleStacked);
    return () => media.removeEventListener("change", handleStacked);
  }, [restore]);

  useEffect(() => () => window.cancelAnimationFrame(frameRef.current ?? 0), []);

  return (
    <div
      className="panel-resize"
      ref={rootRef}
      onFocusCapture={() => {
        focusRef.current = true;
      }}
      onBlurCapture={blurPanel}
    >
      <div
        className="panel-separator"
        role="separator"
        tabIndex={0}
        aria-label="Resize details panel"
        aria-controls="map-inspector"
        aria-orientation="vertical"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={width}
        aria-valuetext={`Details panel ${width} pixels wide`}
        onPointerDown={startResize}
        onPointerMove={moveResize}
        onPointerUp={stopResize}
        onPointerCancel={cancelResize}
        onLostPointerCapture={cancelResize}
        onDoubleClick={reset}
        onKeyDown={keyResize}
      />
      <button
        type="button"
        className="panel-reset"
        aria-label="Reset panel width"
        title="Reset panel width"
        onClick={reset}
      >
        <RotateCcw size={12} />
      </button>
    </div>
  );
}
