import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { LayoutControl } from "./Layout";

describe("LayoutControl", () => {
  it("exposes both layouts as a pressed-button group", () => {
    const markup = renderToStaticMarkup(
      <LayoutControl mode="semantic" onChange={vi.fn()} />,
    );

    expect(markup).toContain('role="group"');
    expect(markup).toContain('aria-label="map layout"');
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain("semantic layout active");
    expect(markup).toContain(">semantic</button>");
    expect(markup).toContain(">connections</button>");
  });
});
