import { describe, expect, it } from "vitest";
import type { GraphNode } from "../types";
import { limitGraph, renderCap, renderIds } from "./lod";

function node(id: string, kind: GraphNode["kind"] = "paper"): GraphNode {
  return {
    id,
    kind,
    label: id,
    val: 1,
    color: "#000",
    payload: {} as never,
  } as GraphNode;
}

describe("renderIds", () => {
  it("keeps small maps complete", () => {
    expect(renderIds([node("one"), node("two")], 2)).toBeNull();
  });

  it("samples papers while retaining structure and active nodes", () => {
    const nodes = [
      node("topic", "topic"),
      ...Array.from({ length: 20 }, (_, index) => node(`paper:${index}`)),
    ];
    const first = renderIds(nodes, 5, ["paper:19"])!;
    const second = renderIds(nodes, 5, ["paper:19"])!;

    expect(first).toEqual(second);
    expect(first.has("topic")).toBe(true);
    expect(first.has("paper:19")).toBe(true);
    expect(first.size).toBeGreaterThanOrEqual(6);
  });

  it("scales detail to the device tier", () => {
    expect(renderCap("high")).toBeGreaterThan(renderCap("balanced"));
    expect(renderCap("balanced")).toBeGreaterThan(renderCap("low"));
  });

  it("limits scene nodes and links without losing an active node", () => {
    const graph = {
      nodes: [node("topic", "topic"), node("paper:1"), node("paper:2")],
      links: [
        { source: "topic", target: "paper:1", kind: "paper" as const },
        { source: "topic", target: "paper:2", kind: "paper" as const },
      ],
    };
    const limited = limitGraph(graph, new Set(["topic", "paper:1"]), "paper:2");

    expect(limited.nodes).toHaveLength(3);
    expect(limited.links).toHaveLength(2);
    expect(limitGraph(graph, null)).toBe(graph);
  });
});
