import { describe, expect, it, vi } from "vitest";

vi.mock("react-force-graph-2d", () => ({ default: () => null }));

import { pickDepth, pickRadius } from "./Fallback";

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

describe("2D pointer depth", () => {
  it("compares foreground and packed points in screen pixels", () => {
    const graph = {
      graph2ScreenCoords: () => ({ x: 40, y: 30 }),
    } as never;
    const canvas = {
      ["getBoundingClientRect"]: () => ({ left: 100, top: 50 }),
    } as HTMLCanvasElement;
    const event = { clientX: 143, clientY: 84 } as MouseEvent;
    expect(pickDepth({ x: 0, y: 0 } as never, event, graph, canvas)).toBe(5);
  });
});
