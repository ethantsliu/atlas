import { describe, expect, it } from "vitest";
import { pullCenter, pullSemantic } from "./force";

describe("pullCenter", () => {
  it("pulls every axis toward the scene origin", () => {
    const nodes = [{ x: 10, y: -20, z: 5, vx: 0, vy: 0, vz: 0 }];
    const force = pullCenter(0.1);
    force.initialize(nodes);
    force(0.5);

    expect(nodes[0]).toMatchObject({ vx: -0.5, vy: 1, vz: -0.25 });
  });
});

describe("pullSemantic", () => {
  it("pulls each node toward its embedding coordinate", () => {
    const nodes = [{ x: 0, y: 10, z: -5, sx: 20, sy: 0, sz: 5, vx: 0, vy: 0, vz: 0 }];
    const force = pullSemantic(0.1);
    force.initialize(nodes);
    force(0.5);

    expect(nodes[0]).toMatchObject({ vx: 1, vy: -0.5, vz: 0.5 });
  });
});
