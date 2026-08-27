import type { GraphNode } from "../../types";

type CloudGate = {
  block: () => void;
  drop: () => void;
  take: () => boolean;
};

export function pickFront(
  cloud: CloudGate,
  open: { current: boolean },
  choose: (node: GraphNode) => void,
  node: GraphNode,
) {
  if (cloud.take()) return;
  open.current = false;
  cloud.drop();
  cloud.block();
  choose(node);
}
