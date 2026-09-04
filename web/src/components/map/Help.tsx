import { labelOf } from "../../lib/text";
import type { GraphNode } from "../../types";

type HelpProps = {
  cloudLabel: string | null;
  selected: GraphNode | null;
};

export function GraphHelp({ cloudLabel, selected }: HelpProps) {
  return (
    <>
      <p className="sr-only" id="graph-help">
        Arrow keys move between nodes. Select a node to inspect it.
      </p>
      <p id="graph-selection" className="sr-only" aria-live="polite">
        {selected
          ? `${labelOf(selected.kind)} selected: ${selected.label}`
          : cloudLabel
            ? `Paper selected: ${cloudLabel}`
            : ""}
      </p>
    </>
  );
}
