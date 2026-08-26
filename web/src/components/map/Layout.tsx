import type { LayoutMode } from "../../hooks/layout";
import "./layout.css";

const OPTIONS: Array<{ mode: LayoutMode; title: string }> = [
  {
    mode: "semantic",
    title: "position all node kinds in one shared embedding space",
  },
  {
    mode: "connections",
    title: "position nodes by the structure of their links",
  },
];

type LayoutProps = {
  mode: LayoutMode;
  onChange: (mode: LayoutMode) => void;
};

export function LayoutControl({ mode, onChange }: LayoutProps) {
  return (
    <div className="layout-control" role="group" aria-label="map layout">
      {OPTIONS.map((option) => (
        <button
          aria-pressed={mode === option.mode}
          className={mode === option.mode ? "active" : ""}
          key={option.mode}
          onClick={() => onChange(option.mode)}
          title={option.title}
          type="button"
        >
          {option.mode}
        </button>
      ))}
      <span className="sr-only" aria-live="polite">
        {mode} layout active
      </span>
    </div>
  );
}
