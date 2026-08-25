import { describe, expect, it } from "vitest";
import { makeAtlas } from "../test/fixtures";
import { createGraphNodes } from "./graph";
import { findNextNode } from "./nav";

function positioned() {
  const nodes = createGraphNodes(makeAtlas(), 1).slice(0, 4);
  return nodes.map((node, index) => ({
    ...node,
    x: index === 0 ? 0 : index === 1 ? 10 : 0,
    y: index === 2 ? 10 : index === 3 ? -10 : 0,
  }));
}

describe("findNextNode", () => {
  it("starts at the most prominent visible node", () => {
    const nodes = positioned();
    expect(findNextNode(nodes, null, "ArrowRight")?.id).toBe(
      [...nodes].sort(
        (left, right) => right.val - left.val || left.id.localeCompare(right.id),
      )[0].id,
    );
  });

  it("moves spatially in the requested direction", () => {
    const nodes = positioned();
    expect(findNextNode(nodes, nodes[0], "ArrowRight")?.id).toBe(nodes[1].id);
    expect(findNextNode(nodes, nodes[0], "ArrowDown")?.id).toBe(nodes[2].id);
    expect(findNextNode(nodes, nodes[0], "ArrowUp")?.id).toBe(nodes[3].id);
  });
});
