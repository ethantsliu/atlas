import { createElement, type ReactHTMLElement } from "react";
import { labelOf } from "../../lib/text";
import type { GraphNode } from "../../types";

export function nodeTip(node: GraphNode): ReactHTMLElement<HTMLElement> {
  return createElement("span", null, `${labelOf(node.kind)} · ${node.label}`);
}
