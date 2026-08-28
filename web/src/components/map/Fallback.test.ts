import { describe, expect, it, vi } from "vitest";

vi.mock("react-force-graph-2d", () => ({ default: () => null }));

import { pickRadius } from "./Fallback";

describe("2D pointer radius", () => {
  it.each([0.25, 1, 4])(
    "keeps its minimum at eight CSS pixels at %sx zoom",
    (scale) => {
      expect(pickRadius(0, scale) * scale).toBe(8);
    },
  );

  it("covers a large rendered node when that exceeds the minimum", () => {
    expect(pickRadius(100, 1)).toBe(30);
  });
});
