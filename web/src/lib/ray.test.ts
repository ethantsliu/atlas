import { describe, expect, it } from "vitest";
import { hitRadius } from "./ray";

describe("point hit radius", () => {
  it("tracks viewport scale instead of distance from the origin", () => {
    const camera = { fov: 90, position: { x: 1_000, y: 0, z: 16 } };
    const target = { x: 1_000, y: 0, z: 0 };

    expect(hitRadius(camera, target, 800)).toBeCloseTo(0.24);
  });

  it("keeps a finite minimum for degenerate views", () => {
    const camera = { position: { x: 0, y: 0, z: 0 } };
    expect(hitRadius(camera, undefined, 0)).toBe(0.1);
  });
});
