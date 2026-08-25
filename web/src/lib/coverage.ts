import type { Atlas, Paper } from "../types";

export const READING_DEPTHS = [
  "verified",
  "full_text",
  "abstract",
  "metadata",
  "context",
] as const;

export type ReadingDepthCounts = Record<string, number>;

export function countReadingDepths(papers: readonly Paper[]): ReadingDepthCounts {
  return papers.reduce<ReadingDepthCounts>((counts, paper) => {
    counts[paper.reading_depth] = (counts[paper.reading_depth] ?? 0) + 1;
    return counts;
  }, {});
}

export function countSubstantiveReadings(counts: Readonly<ReadingDepthCounts>): number {
  return (counts.verified ?? 0) + (counts.full_text ?? 0);
}

export function percentageOfTotal(count: number, total: number): number {
  return total > 0 ? (count / total) * 100 : 0;
}

export type CoverageSnapshot = {
  collectionEntries: number;
  canonicalRecords: number;
  depthCounts: ReadingDepthCounts;
  abstractEntries: number;
  fulltextExtracted: number;
  fullReadings: number;
  competitiveLandscapes: number;
  sourceAccess: {
    classifiedRecords: number;
    paperRecords: number;
    nonPaperRecords: number;
    adapterSupported: number;
    adapterMissing: number;
    routes: Record<string, number>;
    extractionStatuses: Record<string, number>;
    supportedWithoutReadings: number;
  } | null;
  completionSatisfied: boolean;
  completionRule: string;
};

export function getCoverageSnapshot(atlas: Pick<Atlas, "coverage">): CoverageSnapshot {
  return {
    collectionEntries: atlas.coverage.collection_entries,
    canonicalRecords: atlas.coverage.canonical_records,
    depthCounts: { ...atlas.coverage.entry_reading_depth },
    abstractEntries: atlas.coverage.abstract_entries,
    fulltextExtracted: atlas.coverage.fulltext_extracted,
    fullReadings: atlas.coverage.full_readings,
    competitiveLandscapes: atlas.coverage.competitive_landscapes,
    sourceAccess: {
      classifiedRecords: atlas.coverage.source_access.canonical_records_classified,
      paperRecords: atlas.coverage.source_access.paper_records,
      nonPaperRecords: atlas.coverage.source_access.non_paper_records,
      adapterSupported: atlas.coverage.source_access.adapter_supported,
      adapterMissing: atlas.coverage.source_access.adapter_missing,
      routes: { ...atlas.coverage.source_access.by_route },
      extractionStatuses: {
        ...atlas.coverage.source_access.by_extraction_status,
      },
      supportedWithoutReadings:
        atlas.coverage.source_access.supported_records_without_readings,
    },
    completionSatisfied: atlas.coverage.completion_gate.satisfied,
    completionRule: atlas.coverage.completion_gate.rule,
  };
}
