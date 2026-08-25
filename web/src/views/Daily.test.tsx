import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { DailyDay, DailyIndex } from "../types";
import { DailyView } from "./Daily";

const feed = vi.hoisted(() => ({
  useFeed: vi.fn(),
}));
const search = vi.hoisted(() => ({
  useSearch: vi.fn(),
}));

vi.mock("../hooks/feed", () => feed);
vi.mock("../hooks/search", () => search);

const day: DailyDay = {
  schema_version: 1,
  policy_version: "ml-feed-1",
  date: "2026-08-21",
  generated_at: "2026-08-22T00:00:00Z",
  source: {
    provider: "arXiv",
    query: "submittedDate:[202608210000 TO 202608212359]",
    timezone: "UTC",
    complete: true,
    source_total: 734,
    fetched_count: 734,
    unique_count: 734,
    page_count: 2,
  },
  relevant_count: 1,
  shortlist_count: 1,
  shortlist_ids: ["2608.00001"],
  papers: [
    {
      id: "2608.00001",
      url: "https://arxiv.org/abs/2608.00001",
      title: "Evolutionary learning environments",
      abstract: "We introduce environment generation for reinforcement learning.",
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
      interest: { score: 8.4, reasons: ["priority topics: environment-design"] },
      topics: [
        { id: "environment-design", score: 1, evidence: ["environment generation"] },
      ],
      tricks: [{ id: "evolutionary-search", score: 1, evidence: ["evolutionary"] }],
    },
  ],
};

const index: DailyIndex = {
  schema_version: 1,
  generated_at: "2026-08-22T00:00:00Z",
  days: [
    {
      date: day.date,
      generated_at: day.generated_at,
      source_total: 734,
      fetched_count: 734,
      relevant_count: 1,
      shortlist_count: 1,
      complete: true,
      path: "/data/feed/2026-08-21.json",
    },
  ],
};

describe("daily view", () => {
  it("shows provenance, independent scores, and all-feed controls", () => {
    search.useSearch.mockReturnValue({
      papers: [],
      total: 0,
      loading: false,
      error: null,
    });
    feed.useFeed.mockReturnValue({
      index,
      day,
      selected: day.date,
      loading: false,
      error: null,
      source: "static",
      fallback: false,
      hostedDays: 0,
      select: vi.fn(),
      retry: vi.fn(),
    });

    const markup = renderToStaticMarkup(<DailyView query="" onClearQuery={vi.fn()} />);

    expect(markup).toContain("<b>734</b><span>submissions scanned</span>");
    expect(markup).toContain("All relevant");
    expect(markup).toContain("Interest shortlist");
    expect(markup).toContain("Evolutionary learning environments");
    expect(markup).toContain("8.4");
    expect(markup).toContain("10.0");
    expect(markup).toContain("Complete");
    expect(markup).toContain("Static archive");
  });

  it("offers recovery when loading fails", () => {
    search.useSearch.mockReturnValue({
      papers: [],
      total: 0,
      loading: false,
      error: null,
    });
    feed.useFeed.mockReturnValue({
      index: null,
      day: null,
      selected: "",
      loading: false,
      error: "Daily feed request failed",
      source: "static",
      fallback: true,
      hostedDays: 0,
      select: vi.fn(),
      retry: vi.fn(),
    });

    const markup = renderToStaticMarkup(<DailyView query="" onClearQuery={vi.fn()} />);

    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Retry");
  });

  it("shows hosted historical results", () => {
    const paper = day.papers[0];
    search.useSearch.mockReturnValue({
      papers: [{ ...paper, date: "2026-08-20", shortlisted: true, rank: 0.8 }],
      total: 1,
      loading: false,
      error: null,
    });
    feed.useFeed.mockReturnValue({
      index,
      day,
      selected: day.date,
      loading: false,
      error: null,
      source: "hosted",
      fallback: false,
      hostedDays: 180,
      select: vi.fn(),
      retry: vi.fn(),
    });

    const markup = renderToStaticMarkup(
      <DailyView query="environment" onClearQuery={vi.fn()} />,
    );

    expect(markup).toContain("Hosted search · read only");
    expect(markup).toContain("Searching 180 hosted UTC days");
    expect(markup).toContain("2026-08-20");
  });
});
