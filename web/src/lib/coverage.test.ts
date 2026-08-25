import { describe, expect, it } from "vitest";
import {
  countReadingDepths,
  countSubstantiveReadings,
  getCoverageSnapshot,
  percentageOfTotal,
} from "./coverage";
import { makeAtlas, makePaper } from "../test/fixtures";

describe("coverage helpers", () => {
  it("counts every reading-depth label", () => {
    const counts = countReadingDepths([
      makePaper({ reading_depth: "full_text" }),
      makePaper({ id: "paper-2", reading_depth: "verified" }),
      makePaper({ id: "paper-3", reading_depth: "abstract" }),
    ]);

    expect(counts).toEqual({ full_text: 1, verified: 1, abstract: 1 });
    expect(countSubstantiveReadings(counts)).toBe(2);
  });

  it("avoids NaN for an empty corpus", () => {
    expect(percentageOfTotal(0, 0)).toBe(0);
  });

  it("prefers the embedded authoritative coverage snapshot", () => {
    const atlas = makeAtlas({
      coverage: {
        updated_at: "2026-01-02",
        collection_entries: 10,
        canonical_records: 9,
        entry_reading_depth: { abstract: 6, full_text: 2, metadata: 2 },
        abstract_entries: 8,
        fulltext_extracted: 4,
        full_readings: 2,
        competitive_landscapes: 2,
        canonical_paper_fulltext_extraction_coverage: 4 / 8,
        canonical_paper_full_reading_coverage: 2 / 8,
        extraction_failures: [],
        source_access: {
          canonical_records_classified: 9,
          paper_records: 8,
          non_paper_records: 1,
          adapter_supported: 8,
          adapter_missing: 1,
          by_route: { arxiv: 8, manual_review: 1 },
          by_extraction_status: { full_text_ok: 2, pending: 6, adapter_missing: 1 },
          supported_records_without_readings: 6,
        },
        completion_gate: { satisfied: false, rule: "Authoritative rule" },
      },
    });

    expect(getCoverageSnapshot(atlas)).toMatchObject({
      collectionEntries: 10,
      canonicalRecords: 9,
      depthCounts: { abstract: 6, full_text: 2, metadata: 2 },
      fulltextExtracted: 4,
      fullReadings: 2,
      sourceAccess: {
        classifiedRecords: 9,
        paperRecords: 8,
        nonPaperRecords: 1,
        adapterSupported: 8,
        adapterMissing: 1,
        routes: { arxiv: 8, manual_review: 1 },
        supportedWithoutReadings: 6,
      },
      completionRule: "Authoritative rule",
    });
  });

  it("uses the required coverage ledger without synthesizing a fallback", () => {
    const snapshot = getCoverageSnapshot(makeAtlas());
    expect(snapshot.collectionEntries).toBe(2);
    expect(snapshot.depthCounts).toEqual({ abstract: 1, metadata: 1 });
    expect(snapshot.completionRule).toBe("Test completion rule");
  });
});
