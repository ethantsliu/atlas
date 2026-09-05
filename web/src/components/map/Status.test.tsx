import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WebglStatus } from "./Status";

describe("WebglStatus", () => {
  it("announces fallback and offers a retry after context loss", () => {
    const markup = renderToStaticMarkup(
      <WebglStatus status="lost" requested="3d" onRetry={vi.fn()} />,
    );

    expect(markup).toContain('role="status"');
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain("3D stopped");
    expect(markup).toContain("compatibility view");
    expect(markup).toContain("Retry 3D");
  });

  it("hides the notice while WebGL is healthy", () => {
    expect(
      renderToStaticMarkup(
        <WebglStatus status="ready" requested="3d" onRetry={vi.fn()} />,
      ),
    ).toBe("");
  });

  it("stays hidden when 2D was deliberately requested", () => {
    expect(
      renderToStaticMarkup(
        <WebglStatus status="unsupported" requested="2d" onRetry={vi.fn()} />,
      ),
    ).toBe("");
  });
});
