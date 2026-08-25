import { describe, expect, it, vi } from "vitest";
import type { LayoutGraph } from "./layout";
import {
  applyLayout,
  freeNodes,
  layoutSpec,
  layoutTicks,
  layoutTime,
  pinNodes,
} from "./layout";

type ForceStub = {
  distance: ReturnType<typeof vi.fn>;
  strength: ReturnType<typeof vi.fn>;
};

function makeGraph() {
  const link: ForceStub = { distance: vi.fn(), strength: vi.fn() };
  const charge: ForceStub = { distance: vi.fn(), strength: vi.fn() };
  const writes = new Map<string, unknown>();
  const d3Force = vi.fn(function (name: string, force?: unknown) {
    if (arguments.length > 1) {
      writes.set(name, force);
      return graph;
    }
    if (name === "link") return link;
    if (name === "charge") return charge;
    return undefined;
  });
  const graph = {
    d3Force,
    d3ReheatSimulation: vi.fn(),
  } as unknown as LayoutGraph;
  return { charge, graph, link, writes };
}

describe("layoutSpec", () => {
  it("makes the connection layout more topology driven", () => {
    const semantic = layoutSpec("semantic");
    const connections = layoutSpec("connections");

    expect(connections.anchor).toBe(0);
    expect(connections.link).toBeGreaterThan(semantic.link);
    expect(connections.charge).toBeLessThan(semantic.charge);
  });

  it("removes layout animation when motion is reduced", () => {
    expect(layoutTime(true)).toBe(0);
    expect(layoutTime(false, 600)).toBe(600);
  });

  it("keeps overview motion but freezes dense semantic layouts", () => {
    expect(layoutTicks("semantic", 150)).toBe(150);
    expect(layoutTicks("semantic", 150, true)).toBe(0);
    expect(layoutTicks("connections", 80)).toBe(80);
    expect(layoutTicks("connections", 80, true)).toBe(30);
  });

  it("pins semantic coordinates and releases them for connections", () => {
    const nodes = [
      {
        id: "paper:one",
        kind: "paper" as const,
        label: "One",
        val: 1,
        color: "#000",
        payload: {} as never,
        x: 9,
        y: 8,
        z: 7,
        sx: 1,
        sy: 2,
        sz: 3,
      },
    ];

    pinNodes(nodes);
    expect(nodes[0]).toMatchObject({ x: 1, y: 2, z: 3, fx: 1, fy: 2, fz: 3 });
    freeNodes(nodes);
    expect(nodes[0]).not.toHaveProperty("fx");
    expect(nodes[0]).not.toHaveProperty("fy");
    expect(nodes[0]).not.toHaveProperty("fz");
  });
});

describe("applyLayout", () => {
  it("restores soft semantic physics in overview mode", () => {
    const { graph, link, writes } = makeGraph();

    applyLayout(graph, "semantic");

    expect(writes.get("atlas-center")).toEqual(expect.any(Function));
    expect(writes.get("atlas-semantic")).toEqual(expect.any(Function));
    expect(link.strength).toHaveBeenCalledWith(layoutSpec("semantic").link);
    expect(graph.d3ReheatSimulation).toHaveBeenCalledOnce();
  });

  it("removes embedding anchors in connection mode", () => {
    const { charge, graph, link, writes } = makeGraph();

    applyLayout(graph, "connections");

    expect(writes.get("atlas-semantic")).toBeNull();
    expect(link.distance).toHaveBeenCalledWith(layoutSpec("connections").distance);
    expect(charge.strength).toHaveBeenCalledWith(layoutSpec("connections").charge);
    expect(graph.d3ReheatSimulation).toHaveBeenCalledOnce();
  });

  it("can configure an engine before its first safe reheat", () => {
    const { graph, writes } = makeGraph();

    applyLayout(graph, "semantic", false);

    expect(writes.get("atlas-center")).toEqual(expect.any(Function));
    expect(writes.get("atlas-semantic")).toEqual(expect.any(Function));
    expect(graph.d3ReheatSimulation).not.toHaveBeenCalled();
  });

  it("disables semantic physics for dense scenes", () => {
    const { graph, link, writes } = makeGraph();

    applyLayout(graph, "semantic", true, true);

    expect(writes.get("atlas-center")).toBeNull();
    expect(writes.get("atlas-semantic")).toBeNull();
    expect(link.strength).toHaveBeenCalledWith(0);
    expect(graph.d3ReheatSimulation).not.toHaveBeenCalled();
  });
});
