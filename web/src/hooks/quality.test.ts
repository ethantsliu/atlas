import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react", () => ({
  useEffect: () => undefined,
  useMemo: <Value>(make: () => Value) => make(),
  useState: <Value>(initial: Value | (() => Value)) => [
    typeof initial === "function" ? (initial as () => Value)() : initial,
    vi.fn(),
  ],
}));

import { useQuality } from "./quality";

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("useQuality", () => {
  it("reads browser capability hints", () => {
    vi.stubGlobal("navigator", { deviceMemory: 4, hardwareConcurrency: 4 });
    vi.stubGlobal("window", {
      devicePixelRatio: 3,
      matchMedia: () => ({ matches: false }),
    });

    expect(useQuality(2_319, 390, 700)).toMatchObject({
      tier: "low",
      geometryDetail: 6,
      pixelRatioCap: 1,
    });
  });

  it("honors the reduced-motion preference", () => {
    vi.stubGlobal("navigator", { deviceMemory: 16, hardwareConcurrency: 12 });
    vi.stubGlobal("window", {
      devicePixelRatio: 2,
      matchMedia: () => ({ matches: true }),
    });

    expect(useQuality(111, 1440, 900)).toMatchObject({
      tier: "balanced",
      cooldownTicks: 30,
    });
  });
});
