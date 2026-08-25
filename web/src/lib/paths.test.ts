import { describe, expect, it } from "vitest";
import { basePath } from "./paths";

describe("basePath", () => {
  it("joins root and subpath deployments", () => {
    expect(basePath("/data/atlas.json", "/")).toBe("/data/atlas.json");
    expect(basePath("/data/atlas.json", "/atlas/")).toBe("/atlas/data/atlas.json");
    expect(basePath("data/atlas.json", "/atlas")).toBe("/atlas/data/atlas.json");
  });
});
