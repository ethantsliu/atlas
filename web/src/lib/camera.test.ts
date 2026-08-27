import { describe, expect, it, vi } from "vitest";
import {
  formatCamera,
  parseCamera,
  read3d,
  show3d,
  type Camera3d,
  type CameraView,
} from "./camera";
import { fly3d } from "./flight";

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

    expect(show3d(graph, view)).toBe(true);

    expect(camera.position.x).toBeCloseTo(26);
    expect(camera.position.y).toBeCloseTo(20);
    expect(camera.position.z).toBeCloseTo(30);
    expect(read3d(graph)).toEqual(view);
  });

  it("reports when a 3D viewport is not ready", () => {
    const graph = {
      camera: () => ({ position: { x: 0, y: 0, z: 0 } }),
      controls: () => ({}),
      cameraPosition: () => undefined,
    } as Camera3d;
    const view: CameraView = {
      target: [0, 0, 0],
      radius: 16,
      yaw: 0,
      pitch: 0,
    };

    expect(show3d(graph, view)).toBe(false);
    expect(show3d(undefined, view)).toBe(false);
  });

  it("preserves the minimum radius after floating-point projection", () => {
    expect(
      formatCamera({ target: [0, 0, 0], radius: 8 - 1e-12, yaw: 0, pitch: 0 }),
    ).toBe("1_0_0_0_8_0_0");
  });

  it("flies beyond the original target while preserving the orbit vector", () => {
    const target = { x: 10, y: -20, z: 30 };
    const camera = { position: { x: 10, y: -20, z: 130 }, fov: 50 };
    const cameraPosition = vi.fn(
      (position: Partial<typeof target>, lookAt?: typeof target) => {
        Object.assign(camera.position, position);
        Object.assign(target, lookAt);
      },
    );
    const graph = {
      camera: () => camera,
      controls: () => ({ target }),
      cameraPosition,
    } as Camera3d;

    expect(fly3d(graph, 0.4)).toBe(true);
    expect(fly3d(graph, 0.4)).toBe(true);
    expect(fly3d(graph, 0.4)).toBe(true);

    expect(cameraPosition).toHaveBeenCalledTimes(3);
    expect(target).toEqual({ x: 10, y: -20, z: -90 });
    expect(camera.position).toEqual({ x: 10, y: -20, z: 10 });
    expect(camera.position.z).toBeLessThan(30);
    expect(camera.position.z - target.z).toBe(100);
  });

  it("rejects invalid flight and clips the shared target to URL bounds", () => {
    const target = { x: 4_090, y: 0, z: 0 };
    const camera = { position: { x: 4_000, y: 0, z: 0 }, fov: 50 };
    const graph = {
      camera: () => camera,
      controls: () => ({ target }),
      cameraPosition: (position: Partial<typeof target>, lookAt?: typeof target) => {
        Object.assign(camera.position, position);
        Object.assign(target, lookAt);
      },
    } as Camera3d;

    expect(fly3d(undefined, 0.4)).toBe(false);
    expect(fly3d(graph, Number.NaN)).toBe(false);
    expect(fly3d(graph, 0)).toBe(false);
    expect(fly3d(graph, -1)).toBe(true);
    expect(target.x).toBe(4_000);
    expect(fly3d(graph, 10)).toBe(true);
    expect(target.x).toBe(4_096);
    expect(read3d(graph)?.target[0]).toBe(4_096);
  });
});
