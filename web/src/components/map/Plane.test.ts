import { describe, expect, it, vi } from "vitest";
import type { CloudData } from "../../lib/cloud";
import { buildCloud, dropCloud } from "../../lib/swarm";
import { movePlane, planeDepth, planeRatio, watchPlane } from "./Plane";

function cloud(loaded = 2): CloudData {
  return {
    positions: new Float32Array([10, 20, 4, -30, 8, -2]),
    scopes: new Uint8Array(2),
    ranges: [],
    loaded,
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
  it("prevents context loss and exposes restoration", () => {
    const element = new EventTarget() as HTMLCanvasElement;
    const lost = vi.fn();
    const restored = vi.fn();
    const stop = watchPlane(element, lost, restored);
    const event = new Event("webglcontextlost", { cancelable: true });

    element.dispatchEvent(event);
    element.dispatchEvent(new Event("webglcontextrestored"));

    expect(event.defaultPrevented).toBe(true);
    expect(lost).toHaveBeenCalledOnce();
    expect(restored).toHaveBeenCalledOnce();
    stop();
    element.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
    expect(lost).toHaveBeenCalledOnce();
  });

  it("caps dense paper clouds at one device pixel", () => {
    expect(planeRatio(99_999, 3)).toBe(1.5);
    expect(planeRatio(100_000, 3)).toBe(1);
    expect(planeRatio(3_100_000, 3)).toBe(1);
  });

  it("measures GPU picks in force graph screen space", () => {
    const event = { clientX: 128, clientY: 99 } as MouseEvent;
    const depth = planeDepth(
      cloud(3_100_000),
      { k: 2, x: 5, y: 5 },
      event,
      canvas(),
      0,
    );
    expect(depth).toBe(5);
  });

  it("rejects a stale GPU index", () => {
    const event = { clientX: 125, clientY: 95 } as MouseEvent;
    expect(planeDepth(cloud(), { k: 2, x: 5, y: 5 }, event, canvas(), 2)).toBe(
      Number.POSITIVE_INFINITY,
    );
  });

  it("draws coarse motion then the full cloud once at rest", () => {
    vi.useFakeTimers();
    const data = cloud();
    const points = buildCloud(data, "light");
    const draw = vi.fn();
    try {
      movePlane(points, draw);
      movePlane(points, draw);
      expect(points.userData.moving).toBe(true);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.coarse);
      expect(draw).toHaveBeenCalledTimes(2);

      vi.advanceTimersByTime(159);
      expect(draw).toHaveBeenCalledTimes(2);
      vi.advanceTimersByTime(1);
      expect(points.userData.moving).toBe(false);
      expect(points.geometry.getAttribute("position")).toBe(points.userData.full);
      expect(points.geometry.drawRange.count).toBe(data.loaded);
      expect(draw).toHaveBeenCalledTimes(3);
    } finally {
      dropCloud(points);
      points.geometry.dispose();
      points.material.dispose();
      vi.useRealTimers();
    }
  });
});
