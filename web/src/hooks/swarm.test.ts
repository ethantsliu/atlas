import { describe, expect, it } from "vitest";
import type { GraphNode } from "../types";
import { bindSwarm, pickSwarm, takeSwarm } from "./swarm";

const paper = { id: "paper-1" } as GraphNode;
const other = { id: "paper-2" } as GraphNode;

describe("paper swarm picking", () => {
  it("binds a click to the visible hovered paper", () => {
    const claim = bindSwarm({ node: paper, x: 100, y: 120 }, null, 102, 121);

    expect(pickSwarm(claim, 102, 121)).toBe(paper);
  });

  it("uses the current ray hit away from the visible label", () => {
    const claim = bindSwarm({ node: paper, x: 100, y: 120 }, other, 140, 160);

    expect(pickSwarm(claim, 140, 160)).toBe(other);
  });

  it("rejects a drag after pointer down", () => {
    const claim = bindSwarm(null, paper, 100, 120);

    expect(pickSwarm(claim, 110, 120)).toBeNull();
  });

  it("keeps ownership until the underlying graph consumes it", () => {
    const claim = { current: true };

    expect(takeSwarm(claim)).toBe(true);
    expect(takeSwarm(claim)).toBe(false);
  });
});
