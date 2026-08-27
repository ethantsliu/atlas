import { describe, expect, it } from "vitest";
import {
  buildCloud,
  buildSwarm,
  cloudOpacity,
  cloudSize,
  markSwarm,
  swarmNode,
} from "./swarm";
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
  it("shrinks full-corpus points without sampling them", () => {
    expect(cloudSize(99_999)).toBe(4.8);
    expect(cloudSize(100_000)).toBe(2.8);
    expect(cloudSize(1_000_000)).toBe(1.8);
    expect(cloudSize(3_000_000)).toBe(1.2);
    expect(cloudSize(5_000_000)).toBe(1);
    expect(cloudOpacity(100_000)).toBe(0.78);
    expect(cloudOpacity(1_000_000)).toBe(0.42);
    expect(cloudOpacity(5_000_000)).toBe(0.24);
  });

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

  it("renders every historical point with one Paper treatment", () => {
    const cloud = buildCloud(
      {
        positions: new Float32Array([1, 2, 3, 4, 5, 6]),
        scopes: new Uint8Array([0, 2]),
        ranges: [],
        loaded: 2,
        radius: 9,
      },
      "dark",
    );

    expect(cloud.geometry.getAttribute("position").count).toBe(2);
    expect(cloud.geometry.getAttribute("scope")).toBeUndefined();
    expect(cloud.geometry.getAttribute("color")).toBeUndefined();
    expect(cloud.geometry.getAttribute("opacity")).toBeUndefined();
    expect(cloud.geometry.getAttribute("scale")).toBeUndefined();
    expect(cloud.material.uniforms.paperColor.value.getHexString()).toBe("83b5bf");
    expect(cloud.material.uniforms.pointOpacity.value).toBe(0.96);
    expect(cloud.material.uniforms.pointSize.value).toBe(4.8);
    expect(cloud.material.vertexShader).not.toContain("scope");

    cloud.geometry.dispose();
    cloud.material.dispose();
  });
});
