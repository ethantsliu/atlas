import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas } from "../../test/fixtures";
import { MapFilters } from "./Filters";

describe("MapFilters", () => {
  it("shows the mapped-paper inventory without unrelated reading-depth coverage", () => {
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
    expect(markup).not.toContain("semantic points");
    expect(markup).not.toContain("paper profiles");
    expect(markup).not.toContain("Profile reading depth");
    expect(markup).not.toContain("Verified + Full Text");
    expect(markup).not.toContain("Metadata");
    expect(markup).not.toContain("Context");
    expect(markup).not.toContain("mapped by semantic similarity");
  });
});
