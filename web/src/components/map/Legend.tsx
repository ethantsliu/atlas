import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";
import { labelOf } from "../../lib/text";

export function GraphLegend() {
  return (
    <div className="legend">
      {ALL_NODE_KINDS.map((kind) => (
        <span key={kind}>
          <i className={kind} style={{ background: NODE_COLORS[kind] }} />
          {labelOf(kind)}
        </span>
      ))}
    </div>
  );
}
