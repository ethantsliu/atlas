import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ViewControl } from "./View";

describe("ViewControl", () => {
  it("exposes both dimensions as a pressed-button group", () => {
    const markup = renderToStaticMarkup(<ViewControl mode="2d" onChange={vi.fn()} />);

    expect(markup).toContain('role="group"');
    expect(markup).toContain('aria-label="map dimension"');
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).toContain(">2D</button>");
    expect(markup).toContain(">3D</button>");
  });
});
