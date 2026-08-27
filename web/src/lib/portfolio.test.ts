import { describe, expect, it } from "vitest";
import { makeIdea } from "../test/fixtures";
import {
  findParentProgram,
  ideaBasis,
  ideaRole,
  ideaStage,
  independentlyRankedIdeas,
  portfolioAtScore,
  visibleProgramGroups,
  workPackagesFor,
} from "./portfolio";

describe("portfolio hierarchy", () => {
  const program = makeIdea({
    id: "program",
    portfolio_role: "program",
    rank_independently: true,
  });
  const workPackage = makeIdea({
    id: "validator",
    portfolio_role: "work-package",
    parent_idea_id: program.id,
    rank_independently: false,
  });
  const standalone = makeIdea({ id: "standalone" });
  const ideas = [program, workPackage, standalone];

  it("resolves explicit roles and parent-child relationships", () => {
    expect(ideaRole(standalone)).toBe("standalone");
    expect(findParentProgram(workPackage, ideas)).toBe(program);
    expect(workPackagesFor(program, ideas)).toEqual([workPackage]);
    expect(independentlyRankedIdeas(ideas)).toEqual([program, standalone]);
  });

  it("describes idea evidence stages without exposing internal origins", () => {
    const researched = makeIdea({
      origin: "user-specified",
      feasibility: { ...standalone.feasibility, screening_estimate: false },
      brief: { ...standalone.brief, status: "researched-draft" },
    });

    expect(ideaStage(standalone)).toBe("Screening candidate");
    expect(ideaBasis(standalone)).toContain("Automatically synthesized");
    expect(ideaStage(researched)).toBe("Researched draft");
    expect(ideaBasis(researched)).toContain("not a validated result");
    expect(ideaBasis(researched)).not.toContain("user-specified");
  });

  it("keeps a matching work package grouped under its program", () => {
    expect(visibleProgramGroups(ideas, new Set([workPackage.id]))).toEqual([
      { program, workPackages: [workPackage] },
    ]);
  });

  it("applies feasibility thresholds to the parent program as one unit", () => {
    const thresholdProgram = {
      ...program,
      feasibility: { ...program.feasibility, score: 6.1 },
    };
    const thresholdWorkPackage = {
      ...workPackage,
      feasibility: { ...workPackage.feasibility, score: 6.6 },
    };
    const thresholdIdeas = [thresholdProgram, thresholdWorkPackage];

    expect(portfolioAtScore(thresholdIdeas, 6.5)).toEqual([]);
    expect(portfolioAtScore(thresholdIdeas, 6)).toEqual([
      thresholdProgram,
      thresholdWorkPackage,
    ]);
  });
});
