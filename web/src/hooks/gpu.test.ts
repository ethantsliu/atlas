import { describe, expect, it } from "vitest";
import { ID_SIZE, PICK_SIZE, pickRadius, readHit } from "./gpu";

function mark(bytes: Uint8Array, x: number, y: number, index: number): void {
  const value = index + 1;
  const offset = (y * PICK_SIZE + x) * 4;
  bytes[offset] = value & 255;
  bytes[offset + 1] = (value >> 8) & 255;
  bytes[offset + 2] = (value >> 16) & 255;
  bytes[offset + 3] = (value >> 24) & 255;
}

describe("GPU pick alignment", () => {
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
