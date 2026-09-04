import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";

const LEGEND_LABELS = {
  topic: "Topics",
  trick: "Techniques",
  paper: "Papers",
  idea: "Ideas",
} as const;

export function GraphLegend({ archive }: { archive: boolean }) {
  return (
    <div className="legend">
      {archive && (
        <span>
          <i
            style={{
              background: NODE_COLORS.paper,
              opacity: 0.4,
            }}
          />
          Archive papers
        </span>
      )}
      {ALL_NODE_KINDS.map((kind) => (
        <span key={kind}>
          <i className={kind} style={{ background: NODE_COLORS[kind] }} />
          {LEGEND_LABELS[kind]}
        </span>
      ))}
    </div>
  );
}
