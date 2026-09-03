import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";
import { labelOf } from "../../lib/text";

export function GraphLegend({ archive = false }: { archive?: boolean }) {
  return (
    <div className="legend">
      {archive && (
        <span title="Archive dots use one opacity; overlapping papers appear brighter">
          <i
            className="archive-paper"
            style={{
              background: "#83b5bf",
              boxShadow: "0 0 0 2px rgba(131, 181, 191, 0.12)",
              height: 4,
              opacity: 0.55,
              width: 4,
            }}
          />
          arXiv archive
        </span>
      )}
      {ALL_NODE_KINDS.map((kind) => (
        <span key={kind}>
          <i className={kind} style={{ background: NODE_COLORS[kind] }} />
          {archive && kind === "paper" ? "Curated paper" : labelOf(kind)}
        </span>
      ))}
    </div>
  );
}
