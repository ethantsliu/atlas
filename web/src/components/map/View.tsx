import type { RenderMode } from "../../hooks/webgl";

type ViewProps = {
  mode: RenderMode;
  onChange: (mode: RenderMode) => void;
};

export function ViewControl({ mode, onChange }: ViewProps) {
  return (
    <div className="layout-control" role="group" aria-label="map dimension">
      <button
        aria-pressed={mode === "2d"}
        className={mode === "2d" ? "active" : ""}
        onClick={() => onChange("2d")}
        type="button"
      >
        2D
      </button>
      <button
        aria-pressed={mode === "3d"}
        className={mode === "3d" ? "active" : ""}
        onClick={() => onChange("3d")}
        type="button"
      >
        3D
      </button>
    </div>
  );
}
