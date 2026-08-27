import type { GraphNode } from "../../types";

type CloudGate = {
  block: () => void;
  drop: () => void;
  take: (node?: GraphNode) => boolean;
};

export function pickFront(
  cloud: CloudGate,
  open: { current: boolean },
  choose: (node: GraphNode) => void,
  node: GraphNode,
) {
  if (cloud.take(node)) return;
  open.current = false;
  cloud.drop();
  cloud.block();
  choose(node);
}
