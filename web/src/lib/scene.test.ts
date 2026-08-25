import { describe, expect, it } from "vitest";
import { makeAtlas } from "../test/fixtures";
import { createGraphNodes } from "./graph";
import { buildNode, LABEL_FONT } from "./scene";

describe("scene cache", () => {
  it("rebuilds a group emptied by WebGL teardown", () => {
    const node = createGraphNodes(makeAtlas(), 1)[0];
    const first = buildNode(node, "light");
    first.clear();

    const recovered = buildNode(node, "light");

    expect(recovered.getObjectByName("shape")).toBeTruthy();
    expect(recovered.getObjectByName("halo")).toBeTruthy();
  });

  it("uses the bundled Baskerville face for interactive labels", () => {
    expect(LABEL_FONT).toBe("Libre Baskerville Variable");
  });
});
