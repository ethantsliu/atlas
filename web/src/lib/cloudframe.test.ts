import { describe, expect, it } from "vitest";
import type { CloudData } from "./cloud";
import {
  CLOUD_VIEW_HORIZONTAL_BIAS,
  CLOUD_VIEW_MARGIN,
  CLOUD_VIEW_VERTICAL_BIAS,
  cloudFrame,
  fitCloudView,
} from "./cloudframe";

function cloud(positions: number[], loaded = positions.length / 3): CloudData {
  return {
    positions: new Float32Array(positions),
    scopes: new Uint8Array(positions.length / 3),
    ranges: [],
    loaded,
    radius: 0,
  };
}

describe("cloud camera frame", () => {
  it("centers the complete cloud instead of the foreground graph", () => {
    const data = cloud([-6, -2, -4, 2, 4, 8]);
    const frame = cloudFrame(data);

    expect(frame?.target).toEqual([-2, 1, 2]);
    expect(frame?.radius).toBeCloseTo(Math.sqrt(61));
  });

  it("waits for every point and leaves room around wide and narrow views", () => {
    const pending = cloud([-10, 0, 0, 10, 0, 0], 1);
    expect(cloudFrame(pending)).toBeNull();

    const data = cloud([-10, 0, 0, 10, 0, 0]);
    const view = {
      target: [10, 20, 30] as const,
      radius: 40,
      yaw: 0,
      pitch: 0,
    };
    expect(fitCloudView(data, view, 800, 400)).toEqual({
      ...view,
      target: [
        10 * CLOUD_VIEW_MARGIN * CLOUD_VIEW_HORIZONTAL_BIAS,
        10 * CLOUD_VIEW_MARGIN * CLOUD_VIEW_VERTICAL_BIAS,
        0,
      ],
      radius: 10 * CLOUD_VIEW_MARGIN,
    });
    expect(fitCloudView(data, view, 400, 800)?.radius).toBe(20 * CLOUD_VIEW_MARGIN);
  });

  it("corrects perspective asymmetry in screen space", () => {
    const data = cloud([0, 10, 9, 0, -10, -9]);
    const view = {
      target: [0, 0, 0] as const,
      radius: 40,
      yaw: 0,
      pitch: 0,
    };

    const fitted = fitCloudView(data, view, 800, 800);

    expect(fitted?.target[1]).toBeGreaterThan(0);
  });
});
