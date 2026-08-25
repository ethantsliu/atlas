import type { GraphNode } from "../types";

export type ArrowKey = "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown";

type PositionedNode = GraphNode & { x: number; y: number };

function hasPoint(node: GraphNode): node is PositionedNode {
  return Number.isFinite(node.x) && Number.isFinite(node.y);
}

function directionFor(key: ArrowKey): [number, number] {
  if (key === "ArrowLeft") return [-1, 0];
  if (key === "ArrowRight") return [1, 0];
  if (key === "ArrowUp") return [0, -1];
  return [0, 1];
}

function navScore(
  origin: PositionedNode,
  candidate: PositionedNode,
  direction: [number, number],
): number {
  const dx = candidate.x - origin.x;
  const dy = candidate.y - origin.y;
  const forward = dx * direction[0] + dy * direction[1];
  const cross = Math.abs(dx * direction[1] - dy * direction[0]);
  return Math.hypot(dx, dy) + cross * 1.5 + (cross / Math.max(forward, 0.01)) * 8;
}

export function findNextNode(
  nodes: readonly GraphNode[],
  selected: GraphNode | null,
  key: ArrowKey,
): GraphNode | null {
  const positioned = nodes.filter(hasPoint);
  if (positioned.length === 0) return nodes[0] ?? null;
  const origin =
    selected && hasPoint(selected)
      ? selected
      : [...positioned].sort(
          (left, right) => right.val - left.val || left.id.localeCompare(right.id),
        )[0];
  if (!selected || !hasPoint(selected)) return origin;

  const direction = directionFor(key);
  const candidates = positioned.filter((candidate) => {
    if (candidate.id === origin.id) return false;
    const dx = candidate.x - origin.x;
    const dy = candidate.y - origin.y;
    return dx * direction[0] + dy * direction[1] > 0;
  });
  return (
    candidates.sort(
      (left, right) =>
        navScore(origin, left, direction) - navScore(origin, right, direction) ||
        left.id.localeCompare(right.id),
    )[0] ?? origin
  );
}
