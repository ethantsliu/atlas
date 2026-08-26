import type { ReactNode } from "react";
import type { LayoutMode } from "../../hooks/layout";

export type RenderMode = "3d" | "2d";

type ControlsProps = {
  count: number;
  mode: RenderMode;
  layout: LayoutMode;
  onReset: () => void;
  children: ReactNode;
};

export function GraphControls({
  count,
  mode,
  layout,
  onReset,
  children,
}: ControlsProps) {
  const space =
    layout === "semantic"
      ? "semantic · embedding-guided similarity"
      : "connections · linked nodes pull together";
  return (
    <>
      <div className="graph-header">
        <div>
          <span className="live-dot" />
          {`${mode === "3d" ? `3D · ${space}` : `2D compatibility · ${space}`} · ${count.toLocaleString()} nodes`}
        </div>
        <span>
          {count > 0
            ? mode === "3d"
              ? "Arrow keys move · drag rotates · scroll/pinch zooms"
              : "Arrow keys move · drag pans · scroll/pinch zooms"
            : "Adjust the active search or lenses"}
        </span>
      </div>

      {count > 0 && (
        <div className="graph-toolbar">
          {children}
          <button className="view-reset" type="button" onClick={onReset}>
            Reset {mode === "3d" ? "3D " : ""}view
          </button>
        </div>
      )}
    </>
  );
}
