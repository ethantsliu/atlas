import { useState } from "react";
import { ChevronDown, SlidersHorizontal, X } from "lucide-react";
import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";
import type { GraphNodeKind } from "../../types";
import type { AtlasRead } from "../../lib/payload";

type MapFiltersProps = {
  atlas: AtlasRead;
  archiveCount?: number;
  kinds: ReadonlySet<GraphNodeKind>;
  focus: string | null;
  minFeasibility: number;
  onToggleKind: (kind: GraphNodeKind) => void;
  onMinFeasibilityChange: (score: number) => void;
  onClearFocus: () => void;
};

const KIND_LABELS: Record<GraphNodeKind, string> = {
  topic: "Topics",
  trick: "Techniques",
  paper: "Papers",
  idea: "Ideas",
};

function countForKind(
  atlas: AtlasRead,
  kind: GraphNodeKind,
  archiveCount?: number,
): number {
  switch (kind) {
    case "topic":
      return atlas.topics.length;
    case "trick":
      return atlas.tricks.length;
    case "paper":
      return atlas.meta.paper_count + (archiveCount ?? 0);
    case "idea":
      return atlas.meta.idea_count;
  }
}

export function MapFilters({
  atlas,
  archiveCount,
  kinds,
  focus,
  minFeasibility,
  onToggleKind,
  onMinFeasibilityChange,
  onClearFocus,
}: MapFiltersProps) {
  const [mobileExpanded, setMobileExpanded] = useState(false);

  return (
    <aside className="filters panel">
      <div className="filter-heading">
        <div className="eyebrow">
          <SlidersHorizontal size={14} /> Lenses
        </div>
        <button
          type="button"
          className="mobile-filter-toggle"
          aria-expanded={mobileExpanded}
          aria-controls="atlas-filter-content"
          onClick={() => setMobileExpanded((expanded) => !expanded)}
        >
          {mobileExpanded ? "Hide filters" : "Show filters"}
          <ChevronDown size={14} aria-hidden="true" />
        </button>
      </div>

      <div
        id="atlas-filter-content"
        className={`filter-content ${mobileExpanded ? "mobile-open" : ""}`}
      >
        {ALL_NODE_KINDS.map((kind) => (
          <button
            className={`kind-toggle ${kinds.has(kind) ? "on" : ""}`}
            onClick={() => onToggleKind(kind)}
            aria-pressed={kinds.has(kind)}
            data-archive-count={kind === "paper" ? archiveCount : undefined}
            key={kind}
          >
            <span style={{ background: NODE_COLORS[kind] }} />
            <span>{KIND_LABELS[kind]}</span>
            <small>{countForKind(atlas, kind, archiveCount).toLocaleString()}</small>
          </button>
        ))}

        <div className="divider" />
        <div className="range-label">
          <span>Minimum feasibility</span>
          <b>{minFeasibility.toFixed(1)}</b>
        </div>
        <input
          className="range"
          type="range"
          min="1"
          max="10"
          step="0.5"
          value={minFeasibility}
          onChange={(event) => onMinFeasibilityChange(Number(event.target.value))}
          aria-label="Minimum feasibility"
        />
        <p className="range-copy">
          Practical testability, not scientific importance. Provisional ideas use
          preliminary feasibility estimates.
        </p>

        <div className="divider" />
        <button className="clear-focus" disabled={!focus} onClick={onClearFocus}>
          <X size={14} /> Show full map
        </button>
        <p className="evidence-note">{atlas.meta.notice}</p>
      </div>
    </aside>
  );
}
