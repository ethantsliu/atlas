import type { Idea, Paper, Taxon } from "../types";

export type FrontierPoint = {
  idea: Idea;
  x: number;
  y: number;
  overlapCount: number;
};

export type TopicEvidenceRow = {
  id: string;
  label: string;
  fullText: number;
  abstract: number;
  metadata: number;
  total: number;
};

export type FeasibilityBin = {
  label: string;
  researched: number;
  screening: number;
  total: number;
};

export type ReadingBalanceRow = {
  id: string;
  label: string;
  papers: number;
  reviewed: number;
  paperShare: number;
  reviewedShare: number;
};

const FRONTIER_BOUNDS = { left: 45, right: 600, top: 20, bottom: 220 } as const;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function layoutFeasibilityFrontier(ideas: readonly Idea[]): FrontierPoint[] {
  const groups = new Map<string, Idea[]>();
  for (const idea of ideas) {
    const key = [idea.brief.confidence, idea.feasibility.score].join("|");
    groups.set(key, [...(groups.get(key) ?? []), idea]);
  }

  return [...groups.values()].flatMap((group) => {
    const ordered = [...group].sort((left, right) => left.id.localeCompare(right.id));
    const baseX = FRONTIER_BOUNDS.left + ordered[0].brief.confidence * 555;
    const baseY =
      FRONTIER_BOUNDS.bottom - ((ordered[0].feasibility.score - 1) / 9) * 200;
    const radius = ordered.length > 1 ? Math.min(15, 5 + ordered.length) : 0;
    const centerX = clamp(
      baseX,
      FRONTIER_BOUNDS.left + radius,
      FRONTIER_BOUNDS.right - radius,
    );
    const centerY = clamp(
      baseY,
      FRONTIER_BOUNDS.top + radius,
      FRONTIER_BOUNDS.bottom - radius,
    );

    return ordered.map((idea, index) => {
      const angle = (2 * Math.PI * index) / ordered.length - Math.PI / 2;
      return {
        idea,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
        overlapCount: ordered.length,
      };
    });
  });
}

export function buildTopicMatrix(papers: readonly Paper[]): Map<string, number> {
  const counts = new Map<string, number>();

  for (const paper of papers) {
    for (const topic of paper.topics) {
      for (const trick of paper.tricks) {
        const key = `${topic.id}|${trick.id}`;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
  }

  return counts;
}

export function buildReadingBalance(
  papers: readonly Paper[],
  reviewedPapers: readonly Paper[],
  topics: readonly Taxon[],
  limit = 10,
): ReadingBalanceRow[] {
  const paperCounts = new Map<string, number>();
  const reviewedCounts = new Map<string, number>();

  for (const paper of papers) {
    for (const route of paper.topics) {
      paperCounts.set(route.id, (paperCounts.get(route.id) ?? 0) + 1);
    }
  }
  for (const paper of reviewedPapers) {
    for (const route of paper.topics) {
      reviewedCounts.set(route.id, (reviewedCounts.get(route.id) ?? 0) + 1);
    }
  }

  return topics
    .map((topic) => ({
      id: topic.id,
      label: topic.label,
      papers: paperCounts.get(topic.id) ?? 0,
      reviewed: reviewedCounts.get(topic.id) ?? 0,
      paperShare: (paperCounts.get(topic.id) ?? 0) / Math.max(1, papers.length),
      reviewedShare:
        (reviewedCounts.get(topic.id) ?? 0) / Math.max(1, reviewedPapers.length),
    }))
    .sort(
      (left, right) =>
        Math.max(right.paperShare, right.reviewedShare) -
          Math.max(left.paperShare, left.reviewedShare) ||
        left.label.localeCompare(right.label),
    )
    .slice(0, limit);
}

export function buildEvidenceRows(
  papers: readonly Paper[],
  topics: readonly Taxon[],
): TopicEvidenceRow[] {
  const selected = new Map(
    topics.map((topic) => [
      topic.id,
      {
        id: topic.id,
        label: topic.label,
        fullText: 0,
        abstract: 0,
        metadata: 0,
        total: 0,
      },
    ]),
  );

  for (const paper of papers) {
    const bucket =
      paper.reading_depth === "full_text" || paper.reading_depth === "verified"
        ? "fullText"
        : paper.reading_depth === "abstract"
          ? "abstract"
          : "metadata";
    for (const route of paper.topics) {
      const row = selected.get(route.id);
      if (!row) continue;
      row[bucket] += 1;
      row.total += 1;
    }
  }

  return topics.map((topic) => selected.get(topic.id)!);
}

export function buildFeasibilityBins(ideas: readonly Idea[]): FeasibilityBin[] {
  const bins = Array.from({ length: 9 }, (_, index) => ({
    label: index === 8 ? "9.0–10.0" : `${index + 1}.0–${index + 1}.9`,
    researched: 0,
    screening: 0,
    total: 0,
  }));

  for (const idea of ideas) {
    const index = Math.min(8, Math.max(0, Math.floor(idea.feasibility.score) - 1));
    const bin = bins[index];
    if (idea.brief.status === "researched-draft") bin.researched += 1;
    else bin.screening += 1;
    bin.total += 1;
  }

  return bins;
}

export function getRecentYears(
  papers: readonly Paper[],
  limit = 12,
): Array<[number, number]> {
  const counts = new Map<number, number>();
  for (const paper of papers) {
    const year = Number(paper.published?.slice(0, 4));
    if (year > 1990) counts.set(year, (counts.get(year) ?? 0) + 1);
  }

  return [...counts].sort((a, b) => a[0] - b[0]).slice(-limit);
}

export function countValues(values: readonly string[]): Record<string, number> {
  return values.reduce<Record<string, number>>((counts, value) => {
    counts[value] = (counts[value] ?? 0) + 1;
    return counts;
  }, {});
}
