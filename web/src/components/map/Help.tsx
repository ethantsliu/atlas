import { labelOf } from "../../lib/text";
import type { GraphNode } from "../../types";
import type { RenderMode } from "./Controls";

type HelpProps = {
  cloudLabel: string | null;
  mode: RenderMode;
  selected: GraphNode | null;
};

export function GraphHelp({ cloudLabel, mode, selected }: HelpProps) {
  return (
    <>
      <p className="sr-only" id="graph-help">
        Use the arrow keys to move between reviewed foreground nodes. Historical swarm
        papers can be inspected with pointer or touch.
        {mode === "3d"
          ? " Drag to rotate the three dimensional map. Scroll to travel through it, or pinch to zoom."
          : " Drag to pan the compatibility map. Scroll or pinch to zoom."}{" "}
        Select a node to inspect it.
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
