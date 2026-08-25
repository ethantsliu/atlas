import { labelOf } from "../../lib/text";
import type { GraphNode } from "../../types";
import type { RenderMode } from "./Controls";

type HelpProps = {
  mode: RenderMode;
  selected: GraphNode | null;
};

export function GraphHelp({ mode, selected }: HelpProps) {
  return (
    <>
      <p className="sr-only" id="graph-help">
        Use the arrow keys to move between visible nodes.
        {mode === "3d"
          ? " Drag to rotate the three dimensional map."
          : " Drag to pan the compatibility map."}{" "}
        Scroll or pinch to zoom. Select a node to inspect it.
      </p>
      <p className="sr-only" aria-live="polite">
        {selected ? `${labelOf(selected.kind)} selected: ${selected.label}` : ""}
      </p>
    </>
  );
}
