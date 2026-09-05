import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";

const LEGEND_LABELS = {
  topic: "Topics",
  trick: "Techniques",
  paper: "Papers",
  idea: "Ideas",
} as const;

export function GraphLegend() {
  return (
    <div className="legend">
      {ALL_NODE_KINDS.map((kind) => (
        <span key={kind}>
          <i className={kind} style={{ background: NODE_COLORS[kind] }} />
          {LEGEND_LABELS[kind]}
        </span>
      ))}
    </div>
  );
}
