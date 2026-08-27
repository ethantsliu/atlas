import { describe, expect, it } from "vitest";
import type { GraphNode } from "../types";
import { pickSwarm, takeSwarm } from "./swarm";

const paper = { id: "paper-1" } as GraphNode;
describe("paper swarm picking", () => {
  it("uses the fresh pointer-down hit", () => {
    const claim = { depth: 4, node: paper, x: 102, y: 121 };
    expect(pickSwarm(claim, 102, 121)).toBe(paper);
  });

  it("rejects a drag after pointer down", () => {
    const claim = { depth: 4, node: paper, x: 100, y: 120 };

    expect(pickSwarm(claim, 110, 120)).toBeNull();
  });

  it("keeps ownership until the underlying graph consumes it", () => {
    const claim = { current: true };

    expect(takeSwarm(claim)).toBe(true);
    expect(takeSwarm(claim)).toBe(false);
  });
});
