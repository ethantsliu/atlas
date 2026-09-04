import { describe, expect, it } from "vitest";
import type { Catalog } from "./catalog";
import {
  DIRECTION_EVIDENCE,
  directionQuestion,
  filterDirectionIdeas,
  projectDirectionIdeas,
} from "./directions";

function catalog(count = 1_710): Catalog {
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
      subjectId: index === 1 ? "stat.ML" : "cs.LG",
      techniqueId: "retrieval-and-memory",
      supportCount: 42 + index,
      yearCount: 8,
      npmi: 0.2,
      supportIds: [`arxiv:2401.${String(index).padStart(5, "0")}`],
    })),
  };
}

describe("corpus-derived direction ideas", () => {
  it("projects every one of the current 1,710 catalog directions", () => {
    const ideas = projectDirectionIdeas(catalog());

    expect(ideas).toHaveLength(1_710);
    expect(new Set(ideas.map((idea) => idea.id))).toHaveLength(1_710);
    expect(ideas[0]).toMatchObject({
      status: "corpus-derived-unreviewed-candidate",
      reviewStatus: "unreviewed",
      noveltyStatus: "not-assessed",
      feasibilityStatus: "not-assessed",
      subjectId: "cs.LG",
      techniqueLabel: "retrieval and memory",
    });
    expect(ideas[0]).not.toHaveProperty("score");
    expect(ideas[0]).not.toHaveProperty("rank");
  });

  it("renders a neutral question and narrow evidence warning", () => {
    expect(directionQuestion("cs.LG", "retrieval and memory")).toBe(
      "Across research classified under cs.LG, under which documented conditions is retrieval and memory associated with better, worse, or unchanged reported outcomes?",
    );
    expect(DIRECTION_EVIDENCE).toContain("source corpus association");
    expect(DIRECTION_EVIDENCE).toContain("not proof of the idea");
    expect(DIRECTION_EVIDENCE).toContain("verify novelty and feasibility");
  });

  it("searches all candidates by subject, method, question, and support ID", () => {
    const ideas = projectDirectionIdeas(catalog(3));

    expect(filterDirectionIdeas(ideas, "stat ml").map((idea) => idea.id)).toEqual([
      ideas[1].id,
    ]);
    expect(filterDirectionIdeas(ideas, "retrieval memory")).toHaveLength(3);
    expect(filterDirectionIdeas(ideas, "better worse")).toHaveLength(3);
    expect(filterDirectionIdeas(ideas, "2401.00002")).toEqual([ideas[2]]);
    expect(filterDirectionIdeas(ideas, "unrelated")).toEqual([]);
  });
});
