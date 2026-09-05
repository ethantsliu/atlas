import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GraphLegend } from "./Legend";

describe("GraphLegend", () => {
  it("shows only graph object kinds", () => {
    const html = renderToStaticMarkup(<GraphLegend />);

    for (const label of ["Topics", "Techniques", "Papers", "Ideas"]) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain("likely ML");
    expect(html).not.toContain("possible ML");
    expect(html).not.toContain("archive context");
  });

  it("presents every paper depth as one Papers category", () => {
    const html = renderToStaticMarkup(<GraphLegend />);
    expect(html.match(/Papers/g)).toHaveLength(1);
    expect(html).not.toContain("Archive papers");
  });
});
