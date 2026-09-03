import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { CloudDetailControl, compactDots } from "./Detail";

describe("CloudDetailControl", () => {
  it("offers a stable overview and the complete cloud", () => {
    const html = renderToStaticMarkup(
      <CloudDetailControl count={3_145_393} detail="sample" onChange={vi.fn()} />,
    );

    expect(compactDots(3_145_393)).toBe("3.15M");
    expect(html).toContain("historical paper dot density");
    expect(html).toContain("100K");
    expect(html).toContain("All 3.15M");
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
