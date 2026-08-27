import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WebGLRenderer } from "three";
import type { CloudData } from "./cloud";
import { CLOUD_BATCH, buildCloud, dropCloud, growCloud } from "./swarm";

let frames: FrameRequestCallback[] = [];

function dataOf(count: number, loaded = 0): CloudData {
  return {
    positions: new Float32Array(count * 3),
    scopes: new Uint8Array(count),
    ranges: [],
    loaded,
    radius: 0,
  };
}

function runFrame(): void {
  const queued = frames;
  frames = [];
  queued.forEach((callback) => callback(performance.now()));
}

beforeEach(() => {
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => vi.unstubAllGlobals());

describe("progressive paper cloud geometry", () => {
  it("grows one stable geometry in bounded animation-frame batches", () => {
    const data = dataOf(CLOUD_BATCH + 2);
    const points = buildCloud(data, "dark");
    const positions = points.geometry.getAttribute("position");

    expect(points.geometry.drawRange).toMatchObject({ start: 0, count: 0 });
    expect(positions.count).toBe(CLOUD_BATCH + 2);
    expect(positions.array).toBe(data.positions);

    data.positions.fill(3);
    data.loaded = CLOUD_BATCH + 2;
    data.radius = 17;
    growCloud(points, data);
    growCloud(points, data);
    expect(frames).toHaveLength(1);
    expect(points.geometry.boundingSphere?.radius).toBe(17);

    runFrame();
    expect(points.geometry.drawRange.count).toBe(CLOUD_BATCH);
    expect(frames).toHaveLength(1);
    expect(points.geometry.getAttribute("position")).toBe(positions);
    expect(points.userData.data).toBe(data);

    runFrame();
    expect(points.geometry.drawRange.count).toBe(CLOUD_BATCH + 2);
    expect(frames).toHaveLength(0);
    expect(points.geometry.getAttribute("position")).toBe(positions);

    points.geometry.dispose();
    points.material.dispose();
  });

  it("allocates the million-point GPU store by byte size and uploads only growth", () => {
    const buffer = {} as WebGLBuffer;
    const bufferSubData = vi.fn();
    const gl = {
      ARRAY_BUFFER: 34_962,
      DYNAMIC_DRAW: 35_048,
      FLOAT: 5_126,
      bindBuffer: vi.fn(),
      bufferData: vi.fn(),
      bufferSubData,
      createBuffer: vi.fn(() => buffer),
      deleteBuffer: vi.fn(),
    } as unknown as WebGL2RenderingContext;
    const renderer = { getContext: () => gl } as unknown as WebGLRenderer;
    const data = dataOf(1_000_000);

    const points = buildCloud(data, "light", renderer);
    const attribute = points.geometry.getAttribute("position");
    expect(
      (attribute as unknown as { isGLBufferAttribute?: boolean }).isGLBufferAttribute,
    ).toBe(true);
    expect(gl.bufferData).toHaveBeenCalledWith(
      gl.ARRAY_BUFFER,
      12_000_000,
      gl.DYNAMIC_DRAW,
    );
    expect(points.geometry.drawRange.count).toBe(0);

    data.positions.set([1, 2, 3, 4, 5, 6]);
    data.loaded = 2;
    data.radius = 9;
    growCloud(points, data);
    runFrame();

    expect(bufferSubData).toHaveBeenCalledOnce();
    expect(bufferSubData.mock.calls[0][0]).toBe(gl.ARRAY_BUFFER);
    expect(bufferSubData.mock.calls[0][1]).toBe(0);
    expect(bufferSubData.mock.calls[0][2]).toBeInstanceOf(Float32Array);
    expect((bufferSubData.mock.calls[0][2] as Float32Array).length).toBe(6);
    expect(points.geometry.drawRange.count).toBe(2);

    dropCloud(points);
    expect(gl.deleteBuffer).toHaveBeenCalledWith(buffer);
    points.geometry.dispose();
    points.material.dispose();
  });
});
