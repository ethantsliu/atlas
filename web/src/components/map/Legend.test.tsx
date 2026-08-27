import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GraphLegend } from "./Legend";

describe("GraphLegend", () => {
  it("shows only graph object kinds", () => {
    const html = renderToStaticMarkup(<GraphLegend />);

    for (const label of ["Topic", "Trick", "Paper", "Idea"]) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain("likely ML");
    expect(html).not.toContain("possible ML");
    expect(html).not.toContain("archive context");
  });
});
