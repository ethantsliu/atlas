import {
  BufferGeometry,
  Float32BufferAttribute,
  PerspectiveCamera,
  Points,
} from "three";
import { describe, expect, it } from "vitest";
import { hitScreen } from "./screen";

function scenePoints(values: number[]): Points {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(values, 3));
  return new Points(geometry);
}

function sceneCamera(): PerspectiveCamera {
  const camera = new PerspectiveCamera(50, 4 / 3, 0.1, 100);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);
  return camera;
}

describe("screen-space point picking", () => {
  const rect = { left: 100, top: 50, width: 400, height: 300 };

  it("accounts for canvas offsets and uses a fixed pixel radius", () => {
    const points = scenePoints([0, 0, 0, 5, 0, 0]);
    expect(hitScreen(points, sceneCamera(), rect, 300, 200)?.index).toBe(0);
    expect(hitScreen(points, sceneCamera(), rect, 307, 200, 6)).toBeNull();
  });

  it("chooses the nearer point when centers overlap", () => {
    const points = scenePoints([0, 0, -4, 0, 0, 1]);
    const hit = hitScreen(points, sceneCamera(), rect, 300, 200);
    expect(hit?.index).toBe(1);
    expect(hit?.depth).toBeCloseTo(9);
  });

  it("respects the geometry draw range", () => {
    const points = scenePoints([4, 0, 0, 0, 0, 0]);
    points.geometry.setDrawRange(0, 1);
    expect(hitScreen(points, sceneCamera(), rect, 300, 200)).toBeNull();
  });
});
