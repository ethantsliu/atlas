import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas } from "../../test/fixtures";
import { MapFilters } from "./Filters";

describe("MapFilters", () => {
  it("shows authoritative inventory counts without implying a hidden archive", () => {
    const atlas = makeAtlas();
    atlas.meta.idea_count = 289;
    const markup = renderToStaticMarkup(
      <MapFilters
        atlas={atlas}
        kinds={new Set(["topic", "trick", "paper", "idea"])}
        focus={null}
        minFeasibility={1}
        onToggleKind={vi.fn()}
        onMinFeasibilityChange={vi.fn()}
        onClearFocus={vi.fn()}
      />,
    );

    expect(markup).toContain("289</small>");
    expect(markup).toContain("2 mapped papers");
    expect(markup).toContain("Broad areas");
    expect(markup).toContain("Technique families");
    expect(markup).toContain("Screened briefs");
    expect(markup).not.toContain("historical arXiv records");
    expect(markup).not.toContain("foreground papers");
  });
});
