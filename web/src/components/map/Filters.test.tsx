import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas } from "../../test/fixtures";
import { MapFilters } from "./Filters";

describe("MapFilters", () => {
  it("separates mapped-paper inventory from Atlas reading-depth coverage", () => {
    const atlas = makeAtlas();
    atlas.meta.idea_count = 289;
    const markup = renderToStaticMarkup(
      <MapFilters
        atlas={atlas}
        archiveCount={3_145_393}
        kinds={new Set(["topic", "trick", "paper", "idea"])}
        focus={null}
        minFeasibility={1}
        onToggleKind={vi.fn()}
        onMinFeasibilityChange={vi.fn()}
        onClearFocus={vi.fn()}
      />,
    );

    expect(markup).toContain("289</small>");
    expect(markup).toContain("Topics");
    expect(markup).toContain("Techniques");
    expect(markup).toContain("Ideas");
    expect(markup).toContain("Papers");
    expect(markup).toContain("3,145,393 semantic map points");
    expect(markup).toContain(
      `${atlas.meta.paper_count.toLocaleString()} paper profiles`,
    );
    expect(markup).toContain(
      `Profile reading depth · ${atlas.coverage.collection_entries.toLocaleString()} papers`,
    );
    expect(markup).toContain("not all 3.15M map points");
    expect(markup).toContain(
      `aria-label="Reading depth for ${atlas.coverage.collection_entries.toLocaleString()} paper profiles"`,
    );
    expect(markup).not.toContain("mapped by semantic similarity");
  });
});
