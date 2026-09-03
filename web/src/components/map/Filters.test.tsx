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
        catalog={{
          sourceCount: 3_148_342,
          broadAreas: 17,
          techniqueFamilies: 24,
          arxivSubjects: 181,
          eligibleDirections: 2_314,
          candidateDirections: 2_000,
          notice: "Candidate directions are not reviewed claims.",
        }}
        kinds={new Set(["topic", "trick", "paper", "idea"])}
        focus={null}
        minFeasibility={1}
        onToggleKind={vi.fn()}
        onMinFeasibilityChange={vi.fn()}
        onClearFocus={vi.fn()}
      />,
    );

    expect(markup).toContain("289</small>");
    expect(markup).toContain("2 papers mapped");
    expect(markup).toContain("181 arXiv subjects");
    expect(markup).toContain("2,000 of 2,314 qualifying candidate directions");
    expect(markup).toContain("289 ideas remain separately screened briefs");
    expect(markup).not.toContain("historical arXiv records");
    expect(markup).not.toContain("foreground papers");
  });
});
