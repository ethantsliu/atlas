import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas, makeIdea } from "../test/fixtures";
import { BriefsView } from "./Briefs";
import { LibraryView } from "./Library";

describe("search states", () => {
  it("exposes semantic Library columns and a distinct row action", () => {
    const markup = renderToStaticMarkup(
      <LibraryView atlas={makeAtlas()} query="" onClearQuery={vi.fn()} />,
    );

    expect(markup).toContain("<table");
    expect(markup).toContain("Collection entry library</caption>");
    expect(markup).toContain('<th scope="col">Entry</th>');
    expect(markup).toContain('<th class="entry-cell" scope="row">');
    expect(markup).toContain('aria-label="Open Alignment Signals details"');
  });

  it("announces and explains empty Library results", () => {
    const markup = renderToStaticMarkup(
      <LibraryView atlas={makeAtlas()} query="missing" onClearQuery={vi.fn()} />,
    );

    expect(markup).toContain('role="status"');
    expect(markup).toContain("0 collection entries match “missing”.");
    expect(markup).toContain("No entries match “missing”");
    expect(markup).toContain("Clear search");
    expect(markup).not.toContain("<table");
  });

  it("announces and explains empty Brief results", () => {
    const markup = renderToStaticMarkup(
      <BriefsView atlas={makeAtlas()} query="missing" onClearQuery={vi.fn()} />,
    );

    expect(markup).toContain('role="status"');
    expect(markup).toContain("0 research or blog briefs match “missing”.");
    expect(markup).toContain("No briefs match “missing”");
    expect(markup).toContain("Clear search");
  });

  it("distinguishes researched drafts, screening candidates, and blog leads", () => {
    const base = makeIdea();
    const researchedBrief = {
      ...base.brief,
      status: "researched-draft" as const,
    };
    const researchedFeasibility = {
      ...base.feasibility,
      screening_estimate: false,
    };
    const program = makeIdea({
      id: "program",
      portfolio_role: "program",
      rank_independently: true,
      feasibility: researchedFeasibility,
      brief: { ...researchedBrief, title: "Research program" },
    });
    const workPackage = makeIdea({
      id: "work-package",
      portfolio_role: "work-package",
      parent_idea_id: program.id,
      rank_independently: false,
      feasibility: researchedFeasibility,
      brief: { ...researchedBrief, title: "Work package" },
    });
    const researchedDraft = makeIdea({
      id: "researched-draft",
      feasibility: researchedFeasibility,
      brief: { ...researchedBrief, title: "Researched draft" },
    });
    const screeningCandidate = makeIdea({
      id: "screening-candidate",
      brief: { ...base.brief, title: "Screening research lead" },
    });
    const blogLead = makeIdea({
      id: "blog-lead",
      kind: "blog",
      brief: { ...base.brief, title: "Provisional blog lead" },
    });
    const markup = renderToStaticMarkup(
      <BriefsView
        atlas={makeAtlas({
          ideas: [program, workPackage, researchedDraft, screeningCandidate, blogLead],
        })}
        query=""
        onClearQuery={vi.fn()}
      />,
    );

    expect(markup).toContain(
      "3 researched drafts · 1 screening candidate · 1 blog lead",
    );
    expect(markup).toContain("Research leads awaiting competitor review");
    expect(markup).toContain("Blog concepts awaiting source development");
    expect(markup).toContain(">screening candidate<");
    expect(markup).toContain(">blog lead<");
    expect(markup).toContain(
      "rank across all independently scored research and blog briefs",
    );
    expect(markup).toContain("#1 portfolio");
  });
});
