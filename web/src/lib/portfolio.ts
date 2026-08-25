import type { Idea } from "../types";

export type ProgramGroup = {
  program: Idea;
  workPackages: Idea[];
};

export function ideaRole(idea: Idea): "program" | "work-package" | "standalone" {
  return idea.portfolio_role ?? "standalone";
}

export function findParentProgram(
  idea: Idea,
  ideas: readonly Idea[],
): Idea | undefined {
  if (ideaRole(idea) !== "work-package" || !idea.parent_idea_id) return undefined;
  return ideas.find((candidate) => candidate.id === idea.parent_idea_id);
}

export function workPackagesFor(program: Idea, ideas: readonly Idea[]): Idea[] {
  return ideas.filter(
    (candidate) =>
      ideaRole(candidate) === "work-package" && candidate.parent_idea_id === program.id,
  );
}

export function independentlyRankedIdeas(ideas: readonly Idea[]): Idea[] {
  return ideas.filter((idea) => idea.rank_independently !== false);
}

export function portfolioAtScore(ideas: readonly Idea[], minimum: number): Idea[] {
  const visibleProgramIds = new Set(
    ideas
      .filter(
        (idea) => ideaRole(idea) === "program" && idea.feasibility.score >= minimum,
      )
      .map((idea) => idea.id),
  );

  return ideas.filter((idea) =>
    ideaRole(idea) === "work-package"
      ? Boolean(idea.parent_idea_id && visibleProgramIds.has(idea.parent_idea_id))
      : idea.feasibility.score >= minimum,
  );
}

export function visibleProgramGroups(
  ideas: readonly Idea[],
  visibleIdeaIds: ReadonlySet<string>,
): ProgramGroup[] {
  return ideas
    .filter((idea) => ideaRole(idea) === "program")
    .map((program) => ({
      program,
      workPackages: workPackagesFor(program, ideas),
    }))
    .filter(
      ({ program, workPackages }) =>
        visibleIdeaIds.has(program.id) ||
        workPackages.some((workPackage) => visibleIdeaIds.has(workPackage.id)),
    );
}
