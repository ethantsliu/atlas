import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { CloudState, PaperState } from "./State";

describe("map loading states", () => {
  it("keeps the paper index copy stable", () => {
    const html = renderToStaticMarkup(
      <PaperState loading error={null} retry={vi.fn()} />,
    );

    expect(html).toContain('role="status"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Loading papers…");
  });

  it("offers a historical paper retry after an error", () => {
    const html = renderToStaticMarkup(
      <CloudState
        loading={false}
        error="Paper cloud request failed (503)"
        retry={vi.fn()}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain(
      "Historical papers unavailable: Paper cloud request failed (503)",
    );
    expect(html).toContain("Retry historical papers");
  });

  it("stays absent while idle", () => {
    expect(
      renderToStaticMarkup(<CloudState loading={false} error={null} retry={vi.fn()} />),
    ).toBe("");
  });
});
