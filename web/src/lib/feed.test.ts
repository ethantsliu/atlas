import { describe, expect, it, vi } from "vitest";
import type { DailyDay, DailyIndex, DailyPaper } from "../types";
import { fetchFeedDay, fetchFeedIndex, isFeedDay, isFeedIndex } from "./feed";

function makePaper(): DailyPaper {
  return {
    id: "2608.00001",
    url: "https://arxiv.org/abs/2608.00001",
    title: "Learning environments",
    abstract: "We introduce a reinforcement learning environment.",
    authors: ["Ada Researcher"],
    categories: ["cs.LG"],
    primary_category: "cs.LG",
    published: "2026-08-21T00:00:00Z",
    updated: "2026-08-21T00:00:00Z",
    comment: "",
    relevance: {
      relevant: true,
      score: 10,
      lane: "core",
      reasons: ["core ML category"],
      strong_hits: ["reinforcement learning"],
      support_hits: [],
    },
    interest: { score: 7.2, reasons: ["priority topics: environment-design"] },
    topics: [{ id: "environment-design", score: 1, evidence: ["environment"] }],
    tricks: [],
  };
}

function makeDay(): DailyDay {
  return {
    schema_version: 1,
    policy_version: "ml-feed-1",
    date: "2026-08-21",
    generated_at: "2026-08-22T00:00:00Z",
    source: {
      provider: "arXiv",
      query: "submittedDate:[202608210000 TO 202608212359]",
      timezone: "UTC",
      complete: true,
      source_total: 1,
      fetched_count: 1,
      unique_count: 1,
      page_count: 1,
    },
    relevant_count: 1,
    shortlist_count: 1,
    shortlist_ids: ["2608.00001"],
    papers: [makePaper()],
  };
}

function makeIndex(): DailyIndex {
  return {
    schema_version: 1,
    generated_at: "2026-08-22T00:00:00Z",
    days: [
      {
        date: "2026-08-21",
        generated_at: "2026-08-22T00:00:00Z",
        source_total: 1,
        fetched_count: 1,
        relevant_count: 1,
        shortlist_count: 1,
        complete: true,
        path: "/data/feed/2026-08-21.json",
      },
    ],
  };
}

describe("daily feed contracts", () => {
  it("accepts a complete index and day", () => {
    expect(isFeedIndex(makeIndex())).toBe(true);
    expect(isFeedDay(makeDay())).toBe(true);
  });

  it("rejects incomplete or count-mismatched days", () => {
    const partial = makeDay();
    partial.source.complete = false;
    expect(isFeedDay(partial)).toBe(false);

    const mismatched = makeDay();
    mismatched.relevant_count = 2;
    expect(isFeedDay(mismatched)).toBe(false);
  });

  it("rejects an untrusted day path", async () => {
    await expect(
      fetchFeedDay("https://example.com/day.json", new AbortController().signal),
    ).rejects.toThrow("path is invalid");
  });

  it("fetches index and day through the configured base", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => makeIndex() })
      .mockResolvedValueOnce({ ok: true, json: async () => makeDay() });
    const signal = new AbortController().signal;

    await fetchFeedIndex(signal, fetcher, "/atlas/");
    await fetchFeedDay("/data/feed/2026-08-21.json", signal, fetcher, "/atlas/");

    expect(fetcher.mock.calls[0][0]).toBe("/atlas/data/feed/index.json");
    expect(fetcher.mock.calls[1][0]).toBe("/atlas/data/feed/2026-08-21.json");
  });
});
