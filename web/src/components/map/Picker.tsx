import { labelOf } from "../../lib/text";
import type { GraphNode } from "../../types";

type PickerProps = {
  nodes: GraphNode[];
  selectedId: string;
  onChoose: (node: GraphNode) => void;
};

export function NodePicker({ nodes, selectedId, onChoose }: PickerProps) {
  return (
    <label className="graph-node-picker">
      <span className="sr-only">Choose a visible graph node</span>
      <select
        value={selectedId}
        onChange={(event) => {
          const node = nodes.find((item) => item.id === event.target.value);
          if (node) onChoose(node);
        }}
      >
        <option value="">Jump to a visible node…</option>
        {[...nodes]
          .sort((left, right) => left.label.localeCompare(right.label))
          .map((node) => (
            <option value={node.id} key={node.id}>
              {labelOf(node.kind)} · {node.label}
            </option>
          ))}
      </select>
    </label>
  );
}
