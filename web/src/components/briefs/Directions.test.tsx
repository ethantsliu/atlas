import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Catalog } from "../../lib/catalog";
import { DirectionIdeasList } from "./Directions";
import directionSource from "./Directions.tsx?raw";
import briefsSource from "../../views/Briefs.tsx?raw";

function catalog(count = 20): Catalog {
  return {
    summary: {
      corpusDigest: "a".repeat(64),
      catalogDigest: "b".repeat(64),
      policyDigest: "c".repeat(64),
      sourceCount: 3_148_342,
      broadAreas: 17,
      techniqueFamilies: 24,
      arxivSubjects: 176,
      eligibleDirections: count,
      candidateDirections: count,
      notice: "Candidate directions are not reviewed claims.",
    },
    areas: [],
    techniques: [
      {
        id: "retrieval-and-memory",
        label: "retrieval and memory",
        allPaperCount: 100,
        inScopePaperCount: 90,
      },
    ],
    subjects: [],
    directions: Array.from({ length: count }, (_, index) => ({
      id: `direction:${String(index).padStart(64, "0")}`,
      subjectId: index === 19 ? "stat.ML" : "cs.LG",
      techniqueId: "retrieval-and-memory",
      supportCount: 42,
      yearCount: 8,
      npmi: 0.2,
      supportIds: [`arxiv:2401.${String(index).padStart(5, "0")}`],
    })),
  };
}

describe("direction community review presentation", () => {
  it("replaces the capped discovery queue in the Ideas experience", () => {
    expect(briefsSource).toContain(
      "<DirectionReviewQueue query={query} onCount={setDirectionCount} />",
    );
    expect(briefsSource).toContain("directionCount.toLocaleString()");
    expect(briefsSource).not.toContain("DiscoveryReviewQueue");
    expect(directionSource).toContain("fetchCatalog(controller.signal)");
    expect(briefsSource.indexOf("<CandidateGroups")).toBeLessThan(
      briefsSource.indexOf("<DirectionReviewQueue"),
    );
  });

  it("keeps catalog candidates separate from scored Atlas ideas", () => {
    const markup = renderToStaticMarkup(
      <DirectionIdeasList catalog={catalog()} query="" />,
    );

    expect(markup).toContain("20 paper-grounded research ideas");
    expect(markup).toContain("Research ideas for community review");
    expect(markup).toContain("separate from Atlas&#x27;s researched drafts");
    expect(markup).toContain("structured provisional ideas");
    expect(markup).toContain("open for community review");
    expect(markup).toContain("Community members should verify novelty and feasibility");
    expect(markup).not.toContain("card-score");
    expect(markup).not.toMatch(/#[0-9]+ portfolio/);
  });

  it("paginates presentation only after searching every candidate", () => {
    const markup = renderToStaticMarkup(
      <DirectionIdeasList catalog={catalog()} query="stat ml" />,
    );

    expect(markup).toContain("1 paper-grounded research idea match");
    expect(markup).toContain("stat.ML");
    expect(markup).not.toContain("Show 2 more");
    expect(markup).toContain("Search evaluates all 20 ideas before pagination");
  });

  it("offers incremental browsing rather than rendering all rows initially", () => {
    const markup = renderToStaticMarkup(
      <DirectionIdeasList catalog={catalog()} query="" />,
    );

    expect(markup).toContain("Show 2 more · 2 remaining");
    expect(markup).toContain("2401.00017");
    expect(markup).not.toContain("2401.00018");
  });
});
