import { describe, expect, it, vi } from "vitest";
import {
  fetchCatalog,
  fetchCatalogSummary,
  readCatalog,
  readCatalogSummary,
} from "./catalog";

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

function detail() {
  return {
    ...payload(),
    counts: {
      broad_areas: 1,
      technique_families: 1,
      arxiv_subjects: 1,
      eligible_directions: 1,
      candidate_directions: 1,
    },
    areas: [
      {
        id: "agents",
        label: "agents",
        all_paper_count: 120,
        in_scope_paper_count: 100,
      },
    ],
    techniques: [
      {
        id: "retrieval-and-memory",
        label: "retrieval and memory",
        all_paper_count: 90,
        in_scope_paper_count: 80,
      },
    ],
    subjects: [
      {
        id: "cs.LG",
        label: "cs.LG",
        paper_count: 75,
        primary_paper_count: 60,
      },
    ],
    directions: [
      {
        id: "direction:1234567890abcdef",
        status: "candidate",
        subject_id: "cs.LG",
        technique_id: "retrieval-and-memory",
        support_count: 42,
        year_count: 8,
        independent_author_groups_at_least: 3,
        npmi: 0.2,
        support_ids: ["arxiv:2401.00001", "arxiv:2501.00002"],
      },
    ],
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

  it("validates every explorable catalog row and reference", () => {
    expect(readCatalog(detail())).toMatchObject({
      summary: { arxivSubjects: 1, candidateDirections: 1 },
      subjects: [{ id: "cs.LG", paperCount: 75 }],
      directions: [{ techniqueId: "retrieval-and-memory", supportCount: 42 }],
    });

    const duplicate = detail();
    duplicate.counts.candidate_directions = 2;
    duplicate.counts.eligible_directions = 2;
    duplicate.directions.push({ ...duplicate.directions[0] });
    expect(readCatalog(duplicate)).toBeNull();

    const missing = detail();
    missing.directions[0].subject_id = "cs.MISSING";
    expect(readCatalog(missing)).toBeNull();
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

  it("fetches the validated explorable catalog", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(detail())));
    await expect(fetchCatalog(undefined, fetcher, "/atlas/")).resolves.toMatchObject({
      subjects: [{ id: "cs.LG" }],
      directions: [{ id: "direction:1234567890abcdef" }],
    });
  });
});
