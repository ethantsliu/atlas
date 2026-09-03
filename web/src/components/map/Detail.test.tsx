import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-force-graph-3d", () => ({ default: () => null }));

import { CloudDetailControl } from "./Space";

describe("CloudDetailControl", () => {
  it("offers a stable overview and the complete cloud", () => {
    const html = renderToStaticMarkup(
      <CloudDetailControl count={3_145_393} detail="full" onChange={vi.fn()} />,
    );

    expect(html).toContain("historical paper dot density");
    expect(html).toContain("100K");
    expect(html).toContain("All 3.15M");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("Render every 3,145,393 historical paper");
  });

  it("does not offer two identical density modes", () => {
    expect(
      renderToStaticMarkup(
        <CloudDetailControl count={80_000} detail="sample" onChange={vi.fn()} />,
      ),
    ).toBe("");
  });
});
