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
        Arrow keys move between foreground nodes.
        {mode === "3d" ? " Pointer or touch inspects historical papers." : ""}
        {mode === "3d"
          ? " Drag rotates; scroll travels; pinch zooms."
          : " Drag pans; scroll or pinch zooms."}{" "}
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
