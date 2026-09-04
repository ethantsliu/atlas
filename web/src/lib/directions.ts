import type { Catalog, CatalogDirection } from "./catalog";

export const DIRECTION_STATUS = "corpus-derived-unreviewed-candidate" as const;
export const DIRECTION_EVIDENCE =
  "The paper links document the source corpus association, not proof of the idea. Community members should verify novelty and feasibility before building on it.";

export type DirectionIdea = {
  id: string;
  status: typeof DIRECTION_STATUS;
  reviewStatus: "unreviewed";
  noveltyStatus: "not-assessed";
  feasibilityStatus: "not-assessed";
  subjectId: string;
  techniqueId: string;
  techniqueLabel: string;
  question: string;
  supportCount: number;
  yearCount: number;
  supportIds: readonly string[];
};

function normalize(value: string): string {
  return value
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function directionQuestion(subject: string, technique: string): string {
  return `Across research classified under ${subject}, under which documented conditions is ${technique} associated with better, worse, or unchanged reported outcomes?`;
}

function projectDirection(
  direction: CatalogDirection,
  techniques: ReadonlyMap<string, string>,
): DirectionIdea {
  const techniqueLabel = techniques.get(direction.techniqueId) ?? direction.techniqueId;
  return {
    id: direction.id,
    status: DIRECTION_STATUS,
    reviewStatus: "unreviewed",
    noveltyStatus: "not-assessed",
    feasibilityStatus: "not-assessed",
    subjectId: direction.subjectId,
    techniqueId: direction.techniqueId,
    techniqueLabel,
    question: directionQuestion(direction.subjectId, techniqueLabel),
    supportCount: direction.supportCount,
    yearCount: direction.yearCount,
    supportIds: [...direction.supportIds],
  };
}

export function projectDirectionIdeas(catalog: Catalog): DirectionIdea[] {
  const techniques = new Map(catalog.techniques.map((row) => [row.id, row.label]));
  return catalog.directions.map((direction) => projectDirection(direction, techniques));
}

export function filterDirectionIdeas(
  ideas: readonly DirectionIdea[],
  query: string,
): DirectionIdea[] {
  const term = normalize(query);
  if (!term) return [...ideas];
  const terms = term.split(" ");
  return ideas.filter((idea) => {
    const searchable = normalize(
      [
        idea.subjectId,
        idea.techniqueId,
        idea.techniqueLabel,
        idea.question,
        ...idea.supportIds,
      ].join(" "),
    );
    return terms.every((value) => searchable.includes(value));
  });
}
