import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GraphLegend } from "./Legend";

describe("GraphLegend", () => {
  it("shows only graph object kinds", () => {
    const html = renderToStaticMarkup(<GraphLegend archive={false} />);

    for (const label of ["Topics", "Techniques", "Papers", "Ideas"]) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain("likely ML");
    expect(html).not.toContain("possible ML");
    expect(html).not.toContain("archive context");
  });

  it("distinguishes archive papers from foreground papers", () => {
    const html = renderToStaticMarkup(<GraphLegend archive />);
    expect(html).toContain("Archive papers");
    expect(html).toContain("Papers");
    expect(html).not.toContain("Curated");
  });
});
