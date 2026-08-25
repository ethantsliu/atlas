import { describe, expect, it, vi } from "vitest";
import type { HostedConfig } from "./hosted";
import {
  fetchHostedDay,
  fetchHostedIndex,
  hostedConfig,
  searchHostedCorpus,
  searchHostedFeed,
} from "./hosted";

const config: HostedConfig = {
  url: "https://atlas.supabase.co",
  key: "sb_publishable_0123456789abcdefghijklmnop",
};
const legacyAnon =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIn0." +
  "0123456789abcdefghijklmnopqrstuv";

function makeDayRow() {
  return {
    date: "2026-08-21",
    generated_at: "2026-08-22T00:00:00Z",
    policy_version: "ml-feed-1",
    query: "submittedDate:[202608210000 TO 202608212359]",
    source_total: 1,
    fetched_count: 1,
    unique_count: 1,
    page_count: 1,
    relevant_count: 1,
    shortlist_count: 1,
    complete: true,
  };
}

function makePaperRow() {
  return {
    date: "2026-08-21",
    paper_id: "2608.00001",
    shortlisted: true,
    url: "https://arxiv.org/abs/2608.00001",
    title: "Evolutionary learning environments",
    abstract: "We introduce environment generation for reinforcement learning.",
    authors: ["Ada Researcher"],
    categories: ["cs.LG"],
    primary_category: "cs.LG",
    published: "2026-08-21T00:00:00Z",
    updated: "2026-08-21T00:00:00Z",
    comment: "",
    lane: "core",
    relevance_score: 10,
    relevance_reasons: ["core ML category"],
    strong_hits: ["reinforcement learning"],
    support_hits: [],
    interest_score: 8.4,
    interest_reasons: ["priority topic"],
    topics: [{ id: "environment-design", score: 1, evidence: ["environment"] }],
    tricks: [{ id: "evolutionary-search", score: 1, evidence: ["evolutionary"] }],
    rank: 0.72,
    total_count: 42,
  };
}

describe("hosted search contracts", () => {
  it("disables absent configuration", () => {
    expect(hostedConfig({})).toBeNull();
  });

  it("rejects unsafe configuration", () => {
    expect(() => hostedConfig({ VITE_ATLAS_API_URL: "https://atlas.test" })).toThrow(
      "incomplete",
    );
    expect(() =>
      hostedConfig({
        VITE_ATLAS_API_URL: "http://atlas.test",
        VITE_ATLAS_KEY: config.key,
      }),
    ).toThrow("secure service origin");
    expect(() =>
      hostedConfig({
        VITE_ATLAS_API_URL: "https://atlas.test",
        VITE_ATLAS_KEY: "sb_secret_do_not_publish",
      }),
    ).toThrow("invalid");
    for (const key of [
      "public-anon-key",
      `${config.key} `,
      "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
        "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UifQ." +
        "0123456789abcdefghijklmnopqrstuv",
    ]) {
      expect(() =>
        hostedConfig({ VITE_ATLAS_API_URL: "https://atlas.test", VITE_ATLAS_KEY: key }),
      ).toThrow("invalid");
    }
  });

  it("accepts supported public key formats", () => {
    expect(
      hostedConfig({
        VITE_ATLAS_API_URL: "https://atlas.test",
        VITE_ATLAS_KEY: config.key,
      }),
    ).toEqual({ url: "https://atlas.test", key: config.key });
    expect(
      hostedConfig({
        VITE_ATLAS_API_URL: "https://atlas.test",
        VITE_ATLAS_KEY: legacyAnon,
      }),
    ).toEqual({ url: "https://atlas.test", key: legacyAnon });
  });

  it("loads the hosted day index", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [makeDayRow()],
    });

    const index = await fetchHostedIndex(config, new AbortController().signal, fetcher);

    expect(index.days[0].date).toBe("2026-08-21");
    expect(String(fetcher.mock.calls[0][0])).toContain("rest/v1/feed_days");
    expect(fetcher.mock.calls[0][1].headers.apikey).toBe(config.key);
  });

  it("reconstructs a complete hosted day", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [makeDayRow()] })
      .mockResolvedValueOnce({ ok: true, json: async () => [makePaperRow()] });

    const day = await fetchHostedDay(
      config,
      "2026-08-21",
      new AbortController().signal,
      fetcher,
    );

    expect(day.shortlist_ids).toEqual(["2608.00001"]);
    expect(day.papers[0].relevance.lane).toBe("core");
  });

  it("searches with bounded options", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [makePaperRow()],
    });

    const result = await searchHostedFeed(
      config,
      { query: "RL environment", shortlist: false, limit: 30, offset: 30 },
      new AbortController().signal,
      fetcher,
    );

    expect(result.total).toBe(42);
    expect(result.papers[0].date).toBe("2026-08-21");
    const body = JSON.parse(fetcher.mock.calls[0][1].body);
    expect(body).toMatchObject({ page_size: 30, page_offset: 30 });
  });

  it("rejects malformed hosted rows", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => [{}] });

    await expect(
      fetchHostedIndex(config, new AbortController().signal, fetcher),
    ).rejects.toThrow("invalid");
  });

  it("searches the reviewed corpus", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ paper_id: "paper-1", rank: 0.6, total_count: 12 }],
    });

    const result = await searchHostedCorpus(
      config,
      "continual learning",
      100,
      0,
      new AbortController().signal,
      fetcher,
    );

    expect(result.matches).toEqual([{ paperId: "paper-1", rank: 0.6 }]);
    expect(result.total).toBe(12);
    expect(String(fetcher.mock.calls[0][0])).toContain("rpc/search_corpus");
  });
});
