import type { ReactNode } from "react";
import type { LayoutMode } from "../../hooks/layout";
import type { RenderMode } from "../../hooks/webgl";

export type { RenderMode } from "../../hooks/webgl";

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
  const space = layout === "semantic" ? "semantic frame" : "linked structure";
  return (
    <>
      <div className="graph-header">
        <div>
          <span className="live-dot" />
          {`${mode === "3d" ? `3D · ${space}` : `Compatibility · ${space}`} · ${count.toLocaleString()} nodes`}
        </div>
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
