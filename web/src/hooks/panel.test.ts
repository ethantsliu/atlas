import { describe, expect, it } from "vitest";
import {
  PANEL_DEFAULT,
  PANEL_MAX,
  PANEL_MIN,
  clampPanel,
  panelMax,
  readPanel,
} from "./panel";

describe("details panel sizing", () => {
  it("preserves enough graph width on compact desktops", () => {
    expect(panelMax(1_001)).toBe(297);
    expect(panelMax(1_250)).toBe(PANEL_MAX);
  });

  it("clamps stored and dragged widths", () => {
    expect(clampPanel(0, 1_440)).toBe(PANEL_MIN);
    expect(clampPanel(900, 1_440)).toBe(PANEL_MAX);
    expect(clampPanel(Number.NaN, 1_440)).toBe(PANEL_DEFAULT);
  });

  it("accepts only a complete stored integer", () => {
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: { getItem: (key: string) => values.get(key) ?? null },
    });
    values.set("atlas-panel-width-v1", "412");
    expect(readPanel()).toBe(412);
    values.set("atlas-panel-width-v1", "412junk");
    expect(readPanel()).toBe(PANEL_DEFAULT);
    values.set("atlas-panel-width-v1", "900");
    expect(readPanel()).toBe(PANEL_DEFAULT);
  });
});
