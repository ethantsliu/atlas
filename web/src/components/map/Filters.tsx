import { useState } from "react";
import { ChevronDown, SlidersHorizontal, X } from "lucide-react";
import { getCoverageSnapshot } from "../../lib/coverage";
import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";
import { labelOf } from "../../lib/text";
import type { GraphNodeKind } from "../../types";
import type { AtlasRead } from "../../lib/payload";
import { CoverageMini } from "../shared/Coverage";

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
      return atlas.ideas.length;
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
  const coverage = getCoverageSnapshot(atlas);
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
        <p className="aside-copy">
          {archiveCount
            ? `The paper lens batches ${archiveCount.toLocaleString()} historical arXiv records into one semantic swarm. Click or tap a dot to inspect it; reviewed collection papers remain interactive foreground nodes.`
            : `Mix research areas with reusable techniques, paper-grounded ideas, and the ${atlas.meta.paper_count.toLocaleString()}-entry reviewed collection.`}
        </p>

        {ALL_NODE_KINDS.map((kind) => (
          <button
            className={`kind-toggle ${kinds.has(kind) ? "on" : ""}`}
            onClick={() => onToggleKind(kind)}
            aria-pressed={kinds.has(kind)}
            key={kind}
          >
            <span style={{ background: NODE_COLORS[kind] }} />
            <span>{labelOf(kind)}</span>
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
          screening estimates.
        </p>

        <div className="divider" />
        <div className="eyebrow">Entry reading depth</div>
        <p className="depth-copy">
          Full text means a page-anchored reading. Verified adds an independent passage
          and competitor check.
        </p>
        <CoverageMini
          papers={atlas.papers}
          counts={coverage.depthCounts}
          total={coverage.collectionEntries}
        />

        <div className="divider" />
        <button className="clear-focus" disabled={!focus} onClick={onClearFocus}>
          <X size={14} /> Show full map
        </button>
        <p className="evidence-note">{atlas.meta.notice}</p>
      </div>
    </aside>
  );
}
