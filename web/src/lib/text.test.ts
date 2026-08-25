import { describe, expect, it } from "vitest";
import { labelOf } from "./text";

describe("labelOf", () => {
  it("turns machine-readable separators into human-readable labels", () => {
    expect(labelOf("partial_text")).toBe("Partial Text");
    expect(labelOf("gradient-control")).toBe("Gradient Control");
  });
});
