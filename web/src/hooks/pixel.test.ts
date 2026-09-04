import { describe, expect, it, vi } from "vitest";

vi.mock("react", () => ({
  useLayoutEffect: (effect: () => void) => effect(),
}));

import { usePixel } from "./pixel";

describe("pixel density", () => {
  it("caps both the canvas and compositor backing stores", () => {
    vi.stubGlobal("window", { devicePixelRatio: 3 });
    const renderer = { setPixelRatio: vi.fn() };
    const composer = { setPixelRatio: vi.fn() };
    const graphRef = {
      current: {
        renderer: () => renderer,
        postProcessingComposer: () => composer,
      },
    };

    usePixel(graphRef as never, 1);

    expect(renderer.setPixelRatio).toHaveBeenCalledWith(1);
    expect(composer.setPixelRatio).toHaveBeenCalledWith(1);
  });
});
