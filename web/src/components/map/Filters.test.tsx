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
    expect(markup).toContain("Curated topic lenses");
    expect(markup).toContain("Curated technique lenses");
    expect(markup).toContain("Curated briefs");
    expect(markup).toContain("Papers in map");
    expect(markup).not.toContain("historical arXiv records");
    expect(markup).not.toContain("foreground papers");
  });
});
