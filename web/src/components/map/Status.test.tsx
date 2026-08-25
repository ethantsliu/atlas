import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WebglStatus } from "./Status";

describe("WebglStatus", () => {
  it("announces fallback and offers a retry after context loss", () => {
    const markup = renderToStaticMarkup(
      <WebglStatus status="lost" onRetry={vi.fn()} />,
    );

    expect(markup).toContain('role="status"');
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain("3D view paused");
    expect(markup).toContain("2D compatibility view");
    expect(markup).toContain("Retry 3D");
  });

  it("hides the notice while WebGL is healthy", () => {
    expect(renderToStaticMarkup(<WebglStatus status="ready" onRetry={vi.fn()} />)).toBe(
      "",
    );
  });
});
