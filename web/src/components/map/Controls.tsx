import type { ReactNode } from "react";
import type { RenderMode } from "../../hooks/webgl";

export type { RenderMode } from "../../hooks/webgl";

type ControlsProps = {
  count: number;
  mode: RenderMode;
  onReset: () => void;
  children: ReactNode;
};

export function GraphControls({ count, mode, onReset, children }: ControlsProps) {
  return (
    <div className="graph-toolbar">
      <div className="graph-header">
        <div>
          <span className="live-dot" />
          {`${mode === "3d" ? "3D" : "Compatibility"} · ${count.toLocaleString()} nodes`}
        </div>
      </div>
      {count > 0 && (
        <>
          {children}
          <button className="view-reset" type="button" onClick={onReset}>
            Reset {mode === "3d" ? "3D " : ""}view
          </button>
        </>
      )}
    </div>
  );
}
