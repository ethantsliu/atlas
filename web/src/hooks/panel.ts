import { useCallback, useEffect, useMemo, useState } from "react";

export const PANEL_MIN = 280;
export const PANEL_DEFAULT = 330;
export const PANEL_MAX = 520;

const PANEL_KEY = "atlas-panel-width-v1";

export function panelMax(viewport: number): number {
  const filters = viewport <= 1250 ? 224 : 264;
  return Math.max(PANEL_MIN, Math.min(PANEL_MAX, viewport - filters - 480));
}

export function clampPanel(width: number, viewport: number): number {
  const safe = Number.isFinite(width) ? Math.round(width) : PANEL_DEFAULT;
  return Math.min(panelMax(viewport), Math.max(PANEL_MIN, safe));
}

export function readPanel(): number {
  try {
    const value = localStorage.getItem(PANEL_KEY) ?? "";
    const stored = /^\d+$/.test(value) ? Number(value) : Number.NaN;
    return Number.isFinite(stored) && stored >= PANEL_MIN && stored <= PANEL_MAX
      ? stored
      : PANEL_DEFAULT;
  } catch {
    return PANEL_DEFAULT;
  }
}

function savePanel(width: number) {
  try {
    localStorage.setItem(PANEL_KEY, String(Math.round(width)));
  } catch {
    // Storage is an optional convenience; resizing still works without it.
  }
}

function clearPanel() {
  try {
    localStorage.removeItem(PANEL_KEY);
  } catch {
    // A blocked storage API must not affect the inspector.
  }
}

export function usePanel() {
  const [preferred, setPreferred] = useState(readPanel);
  const [viewport, setViewport] = useState(() => window.innerWidth);
  const width = clampPanel(preferred, viewport);
  const max = panelMax(viewport);

  useEffect(() => {
    function readViewport() {
      setViewport(window.innerWidth);
    }
    window.addEventListener("resize", readViewport);
    return () => window.removeEventListener("resize", readViewport);
  }, []);

  const resize = useCallback(
    (next: number) => setPreferred(clampPanel(next, viewport)),
    [viewport],
  );
  const restore = useCallback(
    (next: number) =>
      setPreferred(Math.min(PANEL_MAX, Math.max(PANEL_MIN, Math.round(next)))),
    [],
  );
  const commit = useCallback(
    (next: number) => {
      const safe = clampPanel(next, viewport);
      setPreferred(safe);
      savePanel(safe);
    },
    [viewport],
  );
  const reset = useCallback(() => {
    clearPanel();
    setPreferred(PANEL_DEFAULT);
  }, []);

  return useMemo(
    () => ({ width, preferred, min: PANEL_MIN, max, resize, restore, commit, reset }),
    [commit, max, preferred, reset, resize, restore, width],
  );
}
