import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FactorHeatmap } from "../components/insights/Portfolio";
import { makeAtlas, makeIdea, makePaper } from "../test/fixtures";
import {
  buildFeasibilityBins,
  buildEvidenceRows,
  buildReadingBalance,
  layoutFeasibilityFrontier,
} from "./insights";

describe("layoutFeasibilityFrontier", () => {
  it("separates exact overlaps deterministically", () => {
    const ideas = Array.from({ length: 9 }, (_, index) =>
      makeIdea({ id: "idea-" + index }),
    );

    const first = layoutFeasibilityFrontier(ideas);
    const second = layoutFeasibilityFrontier([...ideas].reverse());
    const coordinates = new Set(
      first.map(({ x, y }) => [x.toFixed(3), y.toFixed(3)].join("|")),
    );

    expect(coordinates.size).toBe(ideas.length);
    expect(first).toEqual(second);
    expect(first.every((point) => point.overlapCount === ideas.length)).toBe(true);
  });

  it("keeps points within the visible plotting area", () => {
    const points = layoutFeasibilityFrontier([
      makeIdea({ brief: { ...makeIdea().brief, confidence: 0 } }),
      makeIdea({
        id: "idea-edge",
        feasibility: { ...makeIdea().feasibility, score: 10 },
        brief: { ...makeIdea().brief, confidence: 1 },
      }),
    ]);

    expect(points.every(({ x }) => x >= 45 && x <= 600)).toBe(true);
    expect(points.every(({ y }) => y >= 20 && y <= 220)).toBe(true);
  });

  it("preserves distinct overlaps at a plotting boundary", () => {
    const ideas = Array.from({ length: 9 }, (_, index) =>
      makeIdea({
        id: `edge-${index}`,
        feasibility: { ...makeIdea().feasibility, score: 10 },
        brief: { ...makeIdea().brief, confidence: 0 },
      }),
    );
    const points = layoutFeasibilityFrontier(ideas);
    const coordinates = new Set(
      points.map(({ x, y }) => [x.toFixed(3), y.toFixed(3)].join("|")),
    );

    expect(coordinates.size).toBe(ideas.length);
    expect(points.every(({ x }) => x >= 45 && x <= 600)).toBe(true);
    expect(points.every(({ y }) => y >= 20 && y <= 220)).toBe(true);
  });
});

describe("buildEvidenceRows", () => {
  it("counts evidence depth independently inside each selected topic", () => {
    const topics = [{ id: "alignment", label: "Alignment", paper_count: 3 }];
    const topicRoute = [{ id: "alignment", score: 1, evidence: ["alignment"] }];
    const rows = buildEvidenceRows(
      [
        makePaper({ id: "full", reading_depth: "full_text", topics: topicRoute }),
        makePaper({ id: "abstract", reading_depth: "abstract", topics: topicRoute }),
        makePaper({ id: "metadata", reading_depth: "metadata", topics: topicRoute }),
        makePaper({ id: "other", topics: [] }),
      ],
      topics,
    );

    expect(rows).toEqual([
      {
        id: "alignment",
        label: "Alignment",
        fullText: 1,
        abstract: 1,
        metadata: 1,
        total: 3,
      },
    ]);
  });
});

describe("buildReadingBalance", () => {
  it("normalizes corpus and full-text footprints independently", () => {
    const topics = [
      { id: "alignment", label: "Alignment", paper_count: 2 },
      { id: "world-models", label: "World Models", paper_count: 1 },
    ];
    const reviewed = makePaper({ reading_depth: "full_text" });
    const rows = buildReadingBalance(
      [
        makePaper(),
        makePaper({ id: "paper-2", topics: makePaper().topics }),
        makePaper({ id: "paper-3", topics: [] }),
      ],
      [reviewed, makePaper({ id: "reviewed-2", topics: [] })],
      topics,
    );

    expect(rows[0]).toMatchObject({
      id: "alignment",
      papers: 2,
      reviewed: 1,
      paperShare: 2 / 3,
      reviewedShare: 1 / 2,
    });
    expect(rows[1]).toMatchObject({
      id: "world-models",
      papers: 0,
      reviewed: 0,
    });
  });
});

describe("FactorHeatmap", () => {
  it("aligns shuffled factors and excludes nested work packages", () => {
    const first = makeIdea({
      id: "first",
      brief: { ...makeIdea().brief, title: "Canonical factors" },
    });
    const shuffled = makeIdea({
      id: "shuffled",
      feasibility: {
        ...makeIdea().feasibility,
        score: 5.7,
        factors: [...makeIdea().feasibility.factors]
          .map((factor) => ({
            ...factor,
            score:
              {
                implementation_leverage: 2.1,
                compute_and_data: 1.8,
                evaluation_clarity: 0.7,
                novelty_risk: 0.2,
                time_to_signal: 0.9,
              }[factor.id] ?? factor.score,
          }))
          .reverse(),
      },
      brief: { ...makeIdea().brief, title: "Shuffled factors" },
    });
    const workPackage = makeIdea({
      id: "nested",
      portfolio_role: "work-package",
      parent_idea_id: first.id,
      rank_independently: false,
      brief: { ...makeIdea().brief, title: "Nested validator" },
    });
    const atlas = makeAtlas({ ideas: [first, shuffled, workPackage] });

    const markup = renderToStaticMarkup(createElement(FactorHeatmap, { atlas }));

    expect(markup).toContain(
      '<tr><th scope="row">Shuffled factors</th><td>5.7</td><td>2.1 / 2.5</td><td>1.8 / 2.5</td><td>0.7 / 2.0</td><td>0.2 / 1.5</td><td>0.9 / 1.5</td></tr>',
    );
    expect(
      markup.indexOf("Shuffled factors — Implementation Leverage: 2.1 / 2.5"),
    ).toBeLessThan(markup.indexOf("Shuffled factors — Compute And Data: 1.8 / 2.5"));
    expect(markup).not.toContain("Nested validator");
  });
});

describe("buildFeasibilityBins", () => {
  it("separates researched drafts from screening estimates in stable score bins", () => {
    const base = makeIdea();
    const withScore = (
      id: string,
      score: number,
      status: "researched-draft" | "provisional",
    ) =>
      makeIdea({
        id,
        feasibility: { ...base.feasibility, score },
        brief: { ...base.brief, status },
      });
    const bins = buildFeasibilityBins([
      withScore("low", 1, "provisional"),
      withScore("six-researched", 6.4, "researched-draft"),
      withScore("six-screening", 6.9, "provisional"),
      withScore("ten", 10, "researched-draft"),
    ]);

    expect(bins).toHaveLength(9);
    expect(bins[0]).toMatchObject({ screening: 1, total: 1 });
    expect(bins[5]).toMatchObject({ researched: 1, screening: 1, total: 2 });
    expect(bins[8]).toMatchObject({ researched: 1, total: 1 });
  });
});
