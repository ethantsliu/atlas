import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";
import { labelOf } from "../../lib/text";

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
          Archive
        </span>
      )}
      {ALL_NODE_KINDS.map((kind) => (
        <span key={kind}>
          <i className={kind} style={{ background: NODE_COLORS[kind] }} />
          {archive && kind === "paper" ? "Curated" : labelOf(kind)}
        </span>
      ))}
    </div>
  );
}
