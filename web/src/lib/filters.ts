import type { GraphNode, Idea, Paper } from "../types";

function includesQuery(value: string, query: string): boolean {
  const normalize = (text: string) =>
    text
      .toLocaleLowerCase()
      .replace(/[-_:]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  return normalize(value).includes(normalize(query));
}

export function filterPaperTitles(papers: readonly Paper[], query: string): Paper[] {
  if (!query.trim()) return [...papers];
  return papers.filter((paper) => includesQuery(paper.title, query));
}

export function filterIdeaQuery(ideas: readonly Idea[], query: string): Idea[] {
  if (!query.trim()) return [...ideas];
  return ideas.filter((idea) =>
    [
      idea.brief.title,
      idea.brief.thesis,
      idea.brief.research_question,
      idea.origin,
      idea.kind,
      ...idea.topic_ids,
      ...idea.trick_ids,
    ].some((field) => includesQuery(field, query)),
  );
}

export function sortIdeaScores(ideas: readonly Idea[]): Idea[] {
  return [...ideas].sort(
    (left, right) => right.feasibility.score - left.feasibility.score,
  );
}

export function findPaperIds(
  papers: readonly Paper[],
  ids: readonly string[],
): Paper[] {
  const requestedIds = new Set(ids);
  return papers.filter(
    (paper) =>
      requestedIds.has(paper.id) ||
      (paper.stable_id !== undefined && requestedIds.has(paper.stable_id)),
  );
}

export function findNodePapers(node: GraphNode, papers: readonly Paper[]): Paper[] {
  switch (node.kind) {
    case "topic":
      return papers.filter((paper) =>
        paper.topics.some((topic) => topic.id === node.payload.id),
      );
    case "trick":
      return papers.filter((paper) =>
        paper.tricks.some((trick) => trick.id === node.payload.id),
      );
    case "idea":
      return findPaperIds(papers, node.payload.brief.paper_ids);
    case "paper":
      return [node.payload];
  }
}
