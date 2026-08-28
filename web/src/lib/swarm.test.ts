import { describe, expect, it, vi } from "vitest";
import { PerspectiveCamera } from "three";
import {
  buildCloud,
  buildSwarm,
  cloudLod,
  cloudOpacity,
  cloudSize,
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
    expect(cloudLod(1_000_000)).toBe(72_000);
    expect(cloudLod(3_150_000)).toBe(100_000);
    expect([...lodIds(10, 4)]).toEqual([1, 3, 6, 8]);
    expect([...lodIds(10, 4)]).toEqual([...lodIds(10, 4)]);
  });

  it("caps motion-only density compensation", () => {
    expect(motionTone(80_000)).toEqual({ opacity: 0.96, size: 4.8 });
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
