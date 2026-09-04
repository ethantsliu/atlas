import { describe, expect, it } from "vitest";
/// <reference types="vite/client" />

import {
  PUBLISHED_METHOD_CANDIDATES,
  catalogDescription,
  candidateQuestion,
} from "./Catalog";
import catalogSource from "./Catalog.tsx?raw";

describe("full-corpus catalog copy", () => {
  it("keeps archive-derived directions separate from Atlas ideas", () => {
    const copy = catalogDescription(
      {
        corpusDigest: "a".repeat(64),
        catalogDigest: "b".repeat(64),
        policyDigest: "c".repeat(64),
        sourceCount: 3_148_342,
        broadAreas: 17,
        techniqueFamilies: 24,
        arxivSubjects: 176,
        eligibleDirections: 1_710,
        candidateDirections: 1_710,
        notice: "Candidate directions are not reviewed claims.",
      },
      310,
    );

    expect(copy).toContain("17 topics and 24 techniques");
    expect(copy).toContain("categories, not corpus totals");
    expect(copy).toContain("176 arXiv subjects");
    expect(copy).toContain(
      "1,710 of 1,710 qualifying unreviewed research-question candidates",
    );
    expect(copy).toContain(
      "310 Atlas ideas are separately reviewed or marked provisional",
    );
  });

  it("projects neutral questions without calling them reviewed ideas", () => {
    expect(candidateQuestion("cs.LG", "retrieval and memory")).toBe(
      "Across research classified under cs.LG, under which documented conditions is retrieval and memory associated with better, worse, or unchanged reported outcomes?",
    );
    expect(catalogSource).toContain("Unreviewed candidate question");
    expect(catalogSource).toMatch(/novelty\s+and feasibility not assessed/);
    expect(catalogSource).toContain('useState<CatalogTab>("questions")');
  });

  it("keeps methods behind the third-layer interaction boundary", () => {
    expect(PUBLISHED_METHOD_CANDIDATES).toBe(129_806);
    expect(catalogSource).toContain('<dl className="catalog-stats"');
    expect(catalogSource).toContain("unreviewed questions");
    expect(catalogSource).toContain("method candidates");
    expect(catalogSource).toContain('lazy(() => import("./Methods"))');
    expect(catalogSource).not.toContain('from "./Methods"');
    expect(catalogSource).toContain("Extracted method phrases");
  });
});
