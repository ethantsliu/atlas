import { describe, expect, it } from "vitest";
import {
  formatCamera,
  parseCamera,
  read3d,
  show3d,
  type Camera3d,
  type CameraView,
} from "./camera";

describe("camera links", () => {
  it("round trips a compact normalized view", () => {
    const view: CameraView = {
      target: [12.34, -45.64, -0],
      radius: 90.04,
      yaw: 35.2,
      pitch: -20.3,
    };
    const encoded = formatCamera(view);
    expect(encoded).toBe("1_12.3_-45.6_0_90_35_-20");
    expect(parseCamera(encoded)).toEqual({
      target: [12.3, -45.6, 0],
      radius: 90,
      yaw: 35,
      pitch: -20,
    });
  });

  it.each([
    "",
    "2_0_0_0_90_0_0",
    "1_NaN_0_0_90_0_0",
    "1_0e2_0_0_90_0_0",
    "1_4097_0_0_90_0_0",
    "1_0_0_0_7_0_0",
    "1_0_0_0_90_181_0",
    "1_0_0_0_90_0_86",
  ])("rejects malformed or unbounded state: %s", (value) => {
    expect(parseCamera(value)).toBeNull();
  });

  it("projects and recovers a 3D viewport", () => {
    const target = { x: 10, y: 20, z: 30 };
    const camera = { position: { x: 0, y: 0, z: 0 }, fov: 90 };
    const graph = {
      camera: () => camera,
      controls: () => ({ target }),
      cameraPosition: (position: Partial<typeof target>, lookAt?: typeof target) => {
        Object.assign(camera.position, position);
        Object.assign(target, lookAt);
      },
    } as Camera3d;
    const view: CameraView = {
      target: [10, 20, 30],
      radius: 16,
      yaw: 90,
      pitch: 0,
    };

    show3d(graph, view);

    expect(camera.position.x).toBeCloseTo(26);
    expect(camera.position.y).toBeCloseTo(20);
    expect(camera.position.z).toBeCloseTo(30);
    expect(read3d(graph)).toEqual(view);
  });

  it("preserves the minimum radius after floating-point projection", () => {
    expect(
      formatCamera({ target: [0, 0, 0], radius: 8 - 1e-12, yaw: 0, pitch: 0 }),
    ).toBe("1_0_0_0_8_0_0");
  });
});
