import type { GraphNode } from "../../types";

type CloudGate = {
  block: () => void;
  drop: () => void;
};

export function pickFront(
  cloud: CloudGate,
  open: { current: boolean },
  choose: (node: GraphNode) => void,
  node: GraphNode,
) {
  open.current = false;
  cloud.drop();
  cloud.block();
  choose(node);
}
