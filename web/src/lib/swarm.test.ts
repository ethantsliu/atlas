import { describe, expect, it } from "vitest";
import { buildCloud, buildSwarm, markSwarm, swarmNode } from "./swarm";
import type { GraphNode } from "../types";

function paper(id: string, x: number): GraphNode {
  return {
    id,
    label: id,
    kind: "paper",
    val: 2,
    color: "#6c8e95",
    payload: {} as GraphNode & never,
    sx: x,
    sy: 2,
    sz: 3,
  } as GraphNode;
}

describe("paper swarm", () => {
  it("batches positioned papers and marks active points", () => {
    const swarm = buildSwarm([paper("paper-1", 1), paper("paper-2", 4)], "light");

    expect(swarm.geometry.getAttribute("position").count).toBe(2);
    expect(swarmNode(swarm, 1)?.id).toBe("paper-2");
    markSwarm(swarm, "paper-1", "paper-2");
    expect(swarm.geometry.getAttribute("scale").getX(0)).toBe(2);
    expect(swarm.geometry.getAttribute("scale").getX(1)).toBeCloseTo(1.55);

    swarm.geometry.dispose();
    swarm.material.dispose();
  });

  it("renders every historical point in one scope-aware draw call", () => {
    const cloud = buildCloud(
      {
        positions: new Float32Array([1, 2, 3, 4, 5, 6]),
        scopes: new Uint8Array([0, 2]),
        ranges: [],
      },
      "dark",
    );

    expect(cloud.geometry.getAttribute("position").count).toBe(2);
    expect(cloud.geometry.getAttribute("opacity").getX(0)).toBeCloseTo(0.9);
    expect(cloud.geometry.getAttribute("opacity").getX(1)).toBeCloseTo(0.24);
    expect(cloud.geometry.getAttribute("scale").getX(0)).toBeCloseTo(1.15);
    expect(cloud.geometry.getAttribute("scale").getX(1)).toBeCloseTo(0.55);
    expect(cloud.material.uniforms.pointSize.value).toBe(4.4);

    cloud.geometry.dispose();
    cloud.material.dispose();
  });
});
