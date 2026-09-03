import { describe, expect, it } from "vitest";
import { catalogDescription } from "./Catalog";

describe("full-corpus catalog copy", () => {
  it("keeps archive-derived directions separate from screened ideas", () => {
    const copy = catalogDescription(
      {
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

    expect(copy).toContain("176 arXiv subjects");
    expect(copy).toContain("1,710 of 1,710 qualifying candidate directions");
    expect(copy).toContain("310 ideas remain separately screened briefs");
  });
});
