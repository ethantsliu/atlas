import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResultStatus } from "./Empty";

describe("result announcements", () => {
  it("mutes progressive count changes until the view is ready", () => {
    const loading = renderToStaticMarkup(
      <ResultStatus count={12} label="node" live={false} query="" />,
    );
    const ready = renderToStaticMarkup(
      <ResultStatus count={24} label="node" live query="" />,
    );

    expect(loading).toContain('aria-live="polite"');
    expect(loading).toContain('role="status"');
    expect(loading).not.toContain("12 nodes available.");
    expect(ready).toContain('aria-live="polite"');
    expect(ready).toContain('role="status"');
    expect(ready).toContain("24 nodes available.");
  });
});
