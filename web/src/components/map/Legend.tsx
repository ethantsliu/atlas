import { ALL_NODE_KINDS, NODE_COLORS } from "../../lib/graph";
import { labelOf } from "../../lib/text";

type LegendProps = {
  history: boolean;
};

export function GraphLegend({ history }: LegendProps) {
  return (
    <div className="legend">
      {ALL_NODE_KINDS.map((kind) => (
        <span key={kind}>
          <i className={kind} style={{ background: NODE_COLORS[kind] }} />
          {labelOf(kind)}
        </span>
      ))}
      {history && (
        <>
          <span>
            <i className="cloud-likely" /> likely ML
          </span>
          <span>
            <i className="cloud-possible" /> possible ML
          </span>
          <span>
            <i className="cloud-context" /> archive context
          </span>
        </>
      )}
    </div>
  );
}
