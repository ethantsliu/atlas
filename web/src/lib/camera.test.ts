import { describe, expect, it } from "vitest";
import { formatCamera, parseCamera, type CameraView } from "./camera";

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
});
