import { describe, expect, it } from "vitest";
import type { CloudData } from "../../lib/cloud";
import { planeHit } from "./Plane";

function cloud(): CloudData {
  return {
    positions: new Float32Array([10, 20, 4, -30, 8, -2]),
    scopes: new Uint8Array(2),
    ranges: [],
    loaded: 2,
    radius: 40,
  };
}

function canvas(): HTMLCanvasElement {
  return {
    ["getBoundingClientRect"]: () =>
      ({ left: 100, top: 50, width: 400, height: 300 }) as DOMRect,
  } as HTMLCanvasElement;
}

describe("2D paper hit", () => {
  it("uses the force graph pan and zoom transform", () => {
    const event = { clientX: 125, clientY: 95 } as MouseEvent;
    const hit = planeHit(cloud(), { k: 2, x: 5, y: 5 }, event, canvas());
    expect(hit.index).toBe(0);
    expect(hit.distance).toBe(0);
  });

  it("does not select points outside the pointer radius", () => {
    const event = { clientX: 300, clientY: 250 } as MouseEvent;
    expect(planeHit(cloud(), { k: 1, x: 0, y: 0 }, event, canvas()).index).toBe(null);
  });
});
