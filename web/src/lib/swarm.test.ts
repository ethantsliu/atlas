import { describe, expect, it, vi } from "vitest";
import { PerspectiveCamera } from "three";
import {
  bindCloud,
  buildCloud,
  buildSwarm,
  CLOUD_REST_MS,
  CLOUD_SETTLE_MS,
  CLOUD_VIEW_EPS,
  cloudBatchEnd,
  cloudLod,
  cloudOpacity,
  cloudSize,
  cloudTone,
  dropCloud,
  lodIds,
  markSwarm,
  moveCloud,
  motionTone,
  restCloud,
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

  it("makes an even deterministic motion level", () => {
    expect(cloudLod(80_000)).toBe(80_000);
    expect(cloudLod(225_000)).toBe(225_000);
    expect(cloudLod(1_000_000)).toBe(72_000);
    expect(cloudLod(3_150_000)).toBe(100_000);
    expect([...lodIds(10, 4)]).toEqual([1, 3, 6, 8]);
    expect([...lodIds(10, 4)]).toEqual([...lodIds(10, 4)]);
  });

  it("catches up when the final cloud pack arrives", () => {
    expect(cloudBatchEnd(0, 65_538, 65_538)).toBe(65_536);
    expect(cloudBatchEnd(0, 200_000, 3_150_000)).toBe(65_536);
    expect(cloudBatchEnd(2_450_000, 3_150_000, 3_150_000)).toBe(3_150_000);
    expect(cloudBatchEnd(0, 200_000, 3_150_000, true)).toBe(200_000);
  });

  it("caps motion-only density compensation", () => {
    expect(motionTone(80_000)).toEqual({ opacity: 0.96, size: 4.8 });
    expect(motionTone(225_000)).toEqual(cloudTone(225_000));
    expect(motionTone(3_151_000).size).toBeCloseTo(2.64);
    expect(motionTone(3_151_000).opacity).toBeCloseTo(0.495);
    expect(motionTone(3_151_000).size / cloudSize(3_151_000)).toBeLessThanOrEqual(2.2);
    expect(motionTone(3_151_000).opacity).toBeLessThanOrEqual(0.72);
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

    moveCloud(cloud);
    expect(cloud.userData.moving).toBe(true);
    expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.coarse);
    expect(cloud.material.uniforms.pointSize.value).toBe(4.8);
    expect(cloud.material.uniforms.pointOpacity.value).toBe(0.96);
    restCloud(cloud);
    expect(cloud.userData.moving).toBe(false);
    expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.full);
    expect(cloud.geometry.drawRange.count).toBe(2);

    dropCloud(cloud);
    cloud.geometry.dispose();
    cloud.material.dispose();
  });

  it("uses motion geometry when the camera changes", () => {
    const redraw = vi.fn();
    const cloud = buildCloud(
      {
        positions: new Float32Array([1, 2, 3, 4, 5, 6]),
        scopes: new Uint8Array([0, 2]),
        ranges: [],
        loaded: 2,
        radius: 9,
      },
      "light",
      undefined,
      redraw,
    );
    const camera = new PerspectiveCamera();
    camera.updateMatrixWorld();
    cloud.onBeforeRender(
      {} as never,
      {} as never,
      camera,
      cloud.geometry,
      cloud.material,
      {} as never,
    );
    expect(cloud.userData.moving).toBe(false);

    camera.position.x = 2;
    camera.updateMatrixWorld();
    cloud.onBeforeRender(
      {} as never,
      {} as never,
      camera,
      cloud.geometry,
      cloud.material,
      {} as never,
    );
    expect(cloud.userData.moving).toBe(true);
    expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.coarse);

    restCloud(cloud);
    expect(redraw).toHaveBeenCalledOnce();
    dropCloud(cloud);
    cloud.geometry.dispose();
    cloud.material.dispose();
  });

  it("ignores sub-threshold camera damping", () => {
    const cloud = buildCloud(
      {
        positions: new Float32Array([1, 2, 3, 4, 5, 6]),
        scopes: new Uint8Array(2),
        ranges: [],
        loaded: 2,
        radius: 9,
      },
      "light",
    );
    const camera = new PerspectiveCamera();
    camera.updateMatrixWorld();
    const render = () =>
      cloud.onBeforeRender(
        {} as never,
        {} as never,
        camera,
        cloud.geometry,
        cloud.material,
        {} as never,
      );
    try {
      render();
      for (const offset of [0.0002, -0.0002, 0.0004, -0.0004]) {
        camera.position.x = offset;
        camera.updateMatrixWorld();
        render();
        expect(cloud.userData.moving).toBe(false);
      }

      camera.position.x = Math.sqrt(CLOUD_VIEW_EPS) * 2;
      camera.updateMatrixWorld();
      render();
      expect(cloud.userData.moving).toBe(true);
      expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.coarse);
    } finally {
      dropCloud(cloud);
      cloud.geometry.dispose();
      cloud.material.dispose();
    }
  });

  it("holds one motion level until gesture damping settles", () => {
    vi.useFakeTimers();
    const redraw = vi.fn();
    const listeners = new Map<string, Set<() => void>>();
    const control = {
      addEventListener: (type: string, listener: () => void) => {
        const group = listeners.get(type) ?? new Set();
        group.add(listener);
        listeners.set(type, group);
      },
      removeEventListener: (type: string, listener: () => void) => {
        listeners.get(type)?.delete(listener);
      },
    };
    const emit = (type: string) =>
      listeners.get(type)?.forEach((listener) => listener());
    const pointer = (type: string, id: number) => {
      const event = new Event(type);
      Object.defineProperty(event, "pointerId", { value: id });
      target.dispatchEvent(event);
    };
    const points = buildCloud(
      {
        positions: new Float32Array([1, 2, 3, 4, 5, 6]),
        scopes: new Uint8Array(2),
        ranges: [],
        loaded: 2,
        radius: 9,
      },
      "light",
      undefined,
      redraw,
    );
    const target = new EventTarget();
    const drop = bindCloud(points, control, target);
    try {
      emit("start");
      emit("end");
      expect(points.userData.moving).toBe(false);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.full);

      moveCloud(points, redraw);
      vi.advanceTimersByTime(CLOUD_REST_MS);
      expect(points.userData.moving).toBe(true);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.coarse);
      vi.advanceTimersByTime(CLOUD_SETTLE_MS - CLOUD_REST_MS);
      expect(points.userData.moving).toBe(false);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.full);
      redraw.mockClear();

      emit("start");
      moveCloud(points, redraw);
      vi.advanceTimersByTime(CLOUD_SETTLE_MS * 2);
      expect(points.userData.moving).toBe(true);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.coarse);
      expect(redraw).not.toHaveBeenCalled();

      emit("end");
      vi.advanceTimersByTime(CLOUD_SETTLE_MS - 1);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.coarse);
      emit("start");
      vi.advanceTimersByTime(CLOUD_SETTLE_MS - 1);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.coarse);

      emit("end");
      vi.advanceTimersByTime(CLOUD_SETTLE_MS - 1);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.coarse);

      vi.advanceTimersByTime(1);
      expect(points.userData.moving).toBe(false);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.full);
      expect(redraw).toHaveBeenCalledOnce();
      vi.advanceTimersByTime(CLOUD_SETTLE_MS * 2);
      expect(redraw).toHaveBeenCalledOnce();

      emit("start");
      pointer("pointerdown", 1);
      emit("start");
      pointer("pointerdown", 2);
      moveCloud(points, redraw);
      pointer("pointercancel", 1);
      emit("end");
      vi.advanceTimersByTime(CLOUD_SETTLE_MS * 2);
      expect(points.userData.moving).toBe(true);
      pointer("pointerup", 2);
      emit("end");
      vi.advanceTimersByTime(CLOUD_SETTLE_MS);
      expect(points.userData.moving).toBe(false);

      emit("start");
      pointer("pointerdown", 3);
      moveCloud(points, redraw);
      pointer("pointercancel", 3);
      emit("end");
      vi.advanceTimersByTime(CLOUD_SETTLE_MS);
      expect(points.userData.moving).toBe(false);
    } finally {
      drop();
      expect(listeners.get("start")).toHaveLength(0);
      expect(listeners.get("end")).toHaveLength(0);
      dropCloud(points);
      points.geometry.dispose();
      points.material.dispose();
      vi.useRealTimers();
    }
  });

  it("restores every one of 3.1M points after motion", () => {
    const count = 3_100_000;
    const cloud = buildCloud(
      {
        positions: new Float32Array(count * 3),
        scopes: new Uint8Array(count),
        ranges: [],
        loaded: count,
        radius: 1,
      },
      "light",
    );
    try {
      expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.full);
      expect(cloud.geometry.drawRange.count).toBe(count);

      moveCloud(cloud);
      expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.coarse);
      expect(cloud.geometry.drawRange.count).toBe(100_000);
      expect(cloud.material.uniforms.pointSize.value).toBeCloseTo(2.64);
      expect(cloud.material.uniforms.pointOpacity.value).toBeCloseTo(0.495);

      restCloud(cloud);
      expect(cloud.geometry.getAttribute("position")).toBe(cloud.userData.full);
      expect(cloud.geometry.drawRange.count).toBe(count);
      expect(cloud.material.uniforms.pointSize.value).toBe(1.2);
      expect(cloud.material.uniforms.pointOpacity.value).toBe(0.3);
    } finally {
      dropCloud(cloud);
      cloud.geometry.dispose();
      cloud.material.dispose();
    }
  });
});
