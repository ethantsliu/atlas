import { describe, expect, it } from "vitest";
import { buildGraph } from "../lib/graph";
import { makeAtlas } from "../test/fixtures";
import type { GraphNode } from "../types";
import { keepGraph } from "./graph";

const kinds = new Set(["topic", "trick", "paper", "idea"] as const);

function makeGraph(query = "") {
  return buildGraph(makeAtlas(), {
    kinds,
    focus: null,
    query,
    minFeasibility: 1,
  });
}

describe("keepGraph", () => {
  it("preserves renderer arrays until topology changes", () => {
    const cache = new Map<string, GraphNode>();
    const first = keepGraph(makeGraph(), undefined, cache);
    const same = keepGraph(makeGraph(), first, cache);
    const changed = keepGraph(makeGraph("alignment"), same, cache);

    expect(same).toBe(first);
    expect(same.graph).toBe(first.graph);
    expect(same.graph.nodes).toBe(first.graph.nodes);
    expect(changed).not.toBe(first);
    expect(changed.graph.nodes).not.toBe(first.graph.nodes);
  });
});
