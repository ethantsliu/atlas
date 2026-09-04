import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas, makeIdea } from "../../test/fixtures";
import { BriefModal } from "./Brief";

vi.mock("../shared/Portal", () => ({
  DialogPortal: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("../../hooks/dialog", () => ({
  useDialog: () => ({ current: null }),
}));

describe("BriefModal", () => {
  it("shows the evidence basis next to the brief claim", () => {
    const idea = makeIdea();
    const markup = renderToStaticMarkup(
      <BriefModal
        idea={idea}
        atlas={makeAtlas()}
        close={vi.fn()}
        onOpenIdea={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(markup).toContain("Evidence basis");
    expect(markup).toContain(idea.brief.evidence_note);
    expect(markup).toContain("Provisional research idea");
    expect(markup).toContain("Preliminary feasibility");
    expect(markup).toContain("Automatically synthesized from corpus routes");
    expect(markup).not.toContain("cross-paper");
  });

  it("labels legacy provenance evidence as Paper", () => {
    const atlas = makeAtlas();
    atlas.papers[0] = {
      ...atlas.papers[0],
      record_kind: "non_paper_context",
      reading_depth: "context",
    };
    const markup = renderToStaticMarkup(
      <BriefModal
        idea={atlas.ideas[0]}
        atlas={atlas}
        close={vi.fn()}
        onOpenIdea={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(markup).toContain("<span>paper</span>");
    expect(markup).not.toContain("<span>context</span>");
  });

  it("renders registered outcomes, analysis, and claim-blocking falsifiers", () => {
    const base = makeIdea();
    const idea = makeIdea({
      brief: {
        ...base.brief,
        experiment: {
          primary_hypothesis: "A registered effect exists.",
          secondary_hypothesis: "The effect transfers.",
          domains: ["Held-out domain"],
          baselines: ["Matched baseline"],
          ablations: ["Remove the mechanism"],
          primary_outcome: "Sealed transfer uplift",
          analysis: "Paired intervals with correction for repeated comparisons.",
          claim_hierarchy: "Primary certificate before secondary controller.",
          selection_protocol: "Freeze the layer rule on development data.",
          resource_scalarization: "Report the nondominated resource set.",
          action_ontology: "Freeze monitor, abstain, patch, and disable actions.",
          decision_rule: "Reject the claim when the interval includes zero.",
        },
        reading_roles: [
          {
            paper_id: base.brief.paper_ids[0],
            role: "substantive support",
            use: "Defines the registered intervention.",
          },
        ],
        route_dictionary_protocol: {
          shared_axes: ["lookup versus inference"],
          markov_family: ["unigram route"],
          regression_family: ["ridge route"],
          freeze_boundary: "Hash routes before confirmation.",
          invalidation_rules: ["Abstain when routes are collinear."],
        },
        milestones: [
          {
            name: "Executable-basis audit",
            deliverable: "Hash-pinned route code",
            pass_condition: "Every planted route is recovered.",
          },
        ],
        competitive_landscape: [
          {
            canonical_id: "arxiv:prior",
            title: "Versioned primary prior",
            url: "https://arxiv.org/abs/prior-v2",
            relationship: "closest prior",
            difference: "It lacks the sealed intervention.",
            provenance_status: "version-verified",
            source_kind: "arxiv",
            source_version: "arXiv:prior-v2",
            source_date: "2026-08-01",
            checked_at: "2026-08-23",
          },
        ],
        novelty_assessment: "The sealed intervention is the remaining delta.",
        falsifiers: ["The target-scale ranking reverses."],
      },
    });
    idea.feasibility.version = "reviewed-v2";
    idea.feasibility.assumptions = ["Public checkpoints remain available."];

    const markup = renderToStaticMarkup(
      <BriefModal
        idea={idea}
        atlas={makeAtlas()}
        close={vi.fn()}
        onOpenIdea={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(markup).toContain("Primary outcome");
    expect(markup).toContain("Sealed transfer uplift");
    expect(markup).toContain("Paired intervals");
    expect(markup).toContain("Claim-blocking falsifiers");
    expect(markup).toContain("target-scale ranking reverses");
    expect(markup).toContain("Revision verified");
    expect(markup).toContain("Claim hierarchy");
    expect(markup).toContain("Selection protocol");
    expect(markup).toContain("Resource scalarization");
    expect(markup).toContain("Action ontology");
    expect(markup).toContain("Frozen route dictionary");
    expect(markup).toContain("Hash routes before confirmation");
    expect(markup).toContain("Milestones and pass conditions");
    expect(markup).toContain("Executable-basis audit");
    expect(markup).toContain("Collection reading roles");
    expect(markup).toContain("substantive support");
    expect(markup).toContain("arXiv:prior-v2");
    expect(markup).toContain("source dated 2026-08-01");
    expect(markup).toContain("Feasibility rubric reviewed-v2");
    expect(markup).toContain("Public checkpoints remain available");
  });

  it("keeps work packages visibly attached to their parent program", () => {
    const program = makeIdea({
      id: "program-1",
      portfolio_role: "program",
      rank_independently: true,
      brief: { ...makeIdea().brief, title: "Environment search program" },
    });
    const workPackage = makeIdea({
      id: "work-package-1",
      portfolio_role: "work-package",
      parent_idea_id: program.id,
      rank_independently: false,
      brief: { ...makeIdea().brief, title: "Prospective scale validator" },
    });
    const atlas = makeAtlas({ ideas: [program, workPackage] });

    const programMarkup = renderToStaticMarkup(
      <BriefModal
        idea={program}
        atlas={atlas}
        close={vi.fn()}
        onOpenIdea={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );
    const workPackageMarkup = renderToStaticMarkup(
      <BriefModal
        idea={workPackage}
        atlas={atlas}
        close={vi.fn()}
        onOpenIdea={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(programMarkup).toContain("Testable work packages");
    expect(programMarkup).toContain("Prospective scale validator");
    expect(workPackageMarkup).toContain("Work package within");
    expect(workPackageMarkup).toContain("Environment search program");
  });

  it("summarizes a dense literature landscape", () => {
    const base = makeIdea();
    const idea = makeIdea({
      brief: {
        ...base.brief,
        competitive_landscape: Array.from({ length: 10 }, (_, index) => ({
          canonical_id: `arxiv:prior-${index}`,
          title: `Competing paper ${index}`,
          url: `https://arxiv.org/abs/prior-${index}`,
          relationship: "direct competitor",
          difference: `Difference ${index}`,
        })),
      },
    });

    const markup = renderToStaticMarkup(
      <BriefModal
        idea={idea}
        atlas={makeAtlas()}
        close={vi.fn()}
        onOpenIdea={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(markup).toContain("10 of 10 papers");
    expect(markup).toContain("Show all 10 papers");
    expect(markup).toContain("Competing paper 7");
    expect(markup).not.toContain("Competing paper 8");
    expect(markup).toContain("Search literature");
  });
});
