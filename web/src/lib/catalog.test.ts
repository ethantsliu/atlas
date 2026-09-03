import { describe, expect, it, vi } from "vitest";
import { fetchCatalogSummary, readCatalogSummary } from "./catalog";

function payload() {
  return {
    schema_version: 1,
    generator_version: "catalog-1",
    status: "corpus-derived",
    corpus: {
      manifest_sha256: "a".repeat(64),
      source_count: 3_148_342,
      month_count: 444,
    },
    coverage: {
      scanned_papers: 3_148_342,
      eligible_direction_papers: 1_562_571,
      scanned_months: 444,
    },
    counts: {
      broad_areas: 17,
      technique_families: 24,
      arxiv_subjects: 181,
      eligible_directions: 2_314,
      candidate_directions: 2_000,
    },
    areas: [],
    techniques: [],
    subjects: [],
    directions: [],
    notice: "Candidate directions are not reviewed claims.",
  };
}

describe("full-corpus catalog", () => {
  it("reads only the compact public inventory", () => {
    expect(readCatalogSummary(payload())).toEqual({
      sourceCount: 3_148_342,
      broadAreas: 17,
      techniqueFamilies: 24,
      arxivSubjects: 181,
      eligibleDirections: 2_314,
      candidateDirections: 2_000,
      notice: "Candidate directions are not reviewed claims.",
    });
  });

  it("rejects inflated or malformed counts", () => {
    const inflated = payload();
    inflated.counts.candidate_directions = 2_315;
    expect(readCatalogSummary(inflated)).toBeNull();
    expect(readCatalogSummary({ ...payload(), extra: true })).toBeNull();
  });

  it("uses the deployed base path", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(payload())));
    await expect(
      fetchCatalogSummary(undefined, fetcher, "/atlas/"),
    ).resolves.toMatchObject({ sourceCount: 3_148_342 });
    expect(fetcher).toHaveBeenCalledWith("/atlas/data/catalog.json", {
      signal: undefined,
      headers: { Accept: "application/json" },
    });
  });
});
