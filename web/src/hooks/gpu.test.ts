import { describe, expect, it } from "vitest";
import {
  BufferGeometry,
  Float32BufferAttribute,
  OrthographicCamera,
  Points,
  ShaderMaterial,
} from "three";
import {
  ID_SIZE,
  PICK_SIZE,
  pickIndex,
  pickRadius,
  pickReady,
  readHit,
  stampPick,
  validPick,
} from "./gpu";

function mark(bytes: Uint8Array, x: number, y: number, index: number): void {
  const value = index + 1;
  const offset = (y * PICK_SIZE + x) * 4;
  bytes[offset] = value & 255;
  bytes[offset + 1] = (value >> 8) & 255;
  bytes[offset + 2] = (value >> 16) & 255;
  bytes[offset + 3] = (value >> 24) & 255;
}

describe("GPU pick alignment", () => {
  it("blocks picking while the cloud uses motion geometry", () => {
    const points = new Points(new BufferGeometry(), new ShaderMaterial());
    expect(pickReady(points)).toBe(true);
    points.userData.moving = true;
    expect(pickReady(points)).toBe(false);
    points.userData.moving = false;
    expect(pickReady(points)).toBe(true);
  });

  it("maps a sampled point back to its full corpus index", () => {
    const geometry = new BufferGeometry();
    const full = new Float32BufferAttribute([0, 0, 0, 1, 1, 1], 3);
    const coarse = new Float32BufferAttribute([1, 1, 1], 3);
    geometry.setAttribute("position", coarse);
    const points = new Points(geometry, new ShaderMaterial());
    points.userData.full = full;
    points.userData.coarse = coarse;
    points.userData.coarseIds = new Uint32Array([1]);

    expect(pickIndex(points, 0)).toBe(1);
    geometry.setAttribute("position", full);
    expect(pickIndex(points, 0)).toBe(0);
  });

  it("keeps full-only alias indices directly pickable", () => {
    const geometry = new BufferGeometry();
    const full = new Float32BufferAttribute([0, 0, 0, 1, 1, 1], 3);
    geometry.setAttribute("position", full);
    const points = new Points(geometry, new ShaderMaterial());
    points.userData.full = full;
    points.userData.coarse = full;
    points.userData.coarseIds = new Uint32Array(0);

    expect(pickIndex(points, 1)).toBe(1);
  });

  it("invalidates an asynchronous pick when the camera moves", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute([0, 0, 0], 3));
    geometry.setDrawRange(0, 1);
    const points = new Points(geometry, new ShaderMaterial());
    const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    camera.position.z = 2;
    const stamp = stampPick(points, camera);

    expect(validPick(stamp, points, camera)).toBe(true);
    camera.position.x = 1;
    expect(validPick(stamp, points, camera)).toBe(false);
  });

  it("invalidates an asynchronous pick when corpus geometry changes", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute([0, 0, 0], 3));
    geometry.setDrawRange(0, 1);
    const points = new Points(geometry, new ShaderMaterial());
    const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    const stamp = stampPick(points, camera);

    geometry.setDrawRange(0, 2);
    expect(validPick(stamp, points, camera)).toBe(false);
    geometry.setDrawRange(0, 1);
    points.userData.moving = true;
    expect(validPick(stamp, points, camera)).toBe(false);
  });

  it("uses a WebKit-safe ID raster without inflating the CSS hit target", () => {
    expect(ID_SIZE).toBe(3);
    expect(pickRadius(8, 400, 300, { width: 400, height: 300 })).toBe(4);
  });

  it("scales CSS hit targets into drawing-buffer pixels", () => {
    expect(pickRadius(24, 400, 300, { width: 400, height: 300 })).toBe(12);
    expect(pickRadius(24, 800, 600, { width: 400, height: 300 })).toBe(24);
    expect(pickRadius(24, 1_200, 900, { width: 400, height: 300 })).toBe(25);
  });

  it("chooses the nearest projected center with top-origin input", () => {
    const bytes = new Uint8Array(PICK_SIZE * PICK_SIZE * 4);
    mark(bytes, 15, PICK_SIZE - 13, 4);
    mark(bytes, 12, PICK_SIZE - 13, 7);

    expect(readHit(bytes, 12.5, 12.5, 0, 0, 10, 8)).toBe(7);
  });

  it("rejects projected centers outside the requested radius", () => {
    const bytes = new Uint8Array(PICK_SIZE * PICK_SIZE * 4);
    mark(bytes, 18, PICK_SIZE - 13, 2);

    expect(readHit(bytes, 12.5, 12.5, 0, 0, 10, 4)).toBeNull();
  });
});
