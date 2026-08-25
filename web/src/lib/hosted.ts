import type {
  DailyDay,
  DailyIndex,
  DailyPaper,
  DailySummary,
  CorpusMatch,
  CorpusResult,
  HostedPaper,
  HostedResult,
} from "../types";
import { isDailyPaper, isFeedDay, isFeedIndex } from "./feed";
import { isNumber, isRecord, isString } from "./guards";

const DAY_VALUE = /^\d{4}-\d{2}-\d{2}$/;
const PUBLISHABLE_KEY = /^sb_publishable_[A-Za-z0-9_-]{20,}$/;
const LEGACY_KEY = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const DAY_SELECT = [
  "date",
  "generated_at",
  "policy_version",
  "query",
  "source_total",
  "fetched_count",
  "unique_count",
  "page_count",
  "relevant_count",
  "shortlist_count",
  "complete",
].join(",");
const PAPER_SELECT = [
  "date",
  "paper_id",
  "shortlisted",
  "url",
  "title",
  "abstract",
  "authors",
  "categories",
  "primary_category",
  "published",
  "updated",
  "comment",
  "lane",
  "relevance_score",
  "relevance_reasons",
  "strong_hits",
  "support_hits",
  "interest_score",
  "interest_reasons",
  "topics",
  "tricks",
].join(",");

export type HostedConfig = {
  url: string;
  key: string;
};

export type SearchOptions = {
  query: string;
  lane?: DailyPaper["relevance"]["lane"];
  shortlist: boolean;
  limit: number;
  offset: number;
};

function legacyPayload(key: string): Record<string, unknown> | null {
  if (!LEGACY_KEY.test(key)) return null;
  try {
    const segment = key.split(".")[1];
    const padded = `${segment}${"=".repeat((4 - (segment.length % 4)) % 4)}`;
    const value: unknown = JSON.parse(
      atob(padded.replace(/-/g, "+").replace(/_/g, "/")),
    );
    return isRecord(value) ? value : null;
  } catch {
    return null;
  }
}

function isHostedKey(key: string): boolean {
  if (key !== key.trim() || key.length > 2048 || /[\s\u0000-\u001f\u007f]/.test(key)) {
    return false;
  }
  if (PUBLISHABLE_KEY.test(key)) return true;
  const payload = legacyPayload(key);
  return payload?.role === "anon" && payload.iss === "supabase";
}

export function hostedConfig(
  env: Record<string, unknown> = import.meta.env,
): HostedConfig | null {
  const rawUrl = env.VITE_ATLAS_API_URL;
  const rawKey = env.VITE_ATLAS_KEY;
  if (!rawUrl && !rawKey) return null;
  if (!isString(rawUrl) || !isString(rawKey) || !rawUrl || !rawKey) {
    throw new Error("Hosted search configuration is incomplete");
  }
  const url = new URL(rawUrl);
  const local = ["localhost", "127.0.0.1"].includes(url.hostname);
  if (
    (url.protocol !== "https:" && !(local && url.protocol === "http:")) ||
    url.pathname !== "/" ||
    url.search
  ) {
    throw new Error("Hosted search URL must be a secure service origin");
  }
  if (url.username || url.password || url.hash || !isHostedKey(rawKey)) {
    throw new Error("Hosted search configuration is invalid");
  }
  return { url: url.origin, key: rawKey };
}

async function requestRows(
  config: HostedConfig,
  path: string,
  signal: AbortSignal,
  fetcher: typeof fetch,
  init: RequestInit = {},
): Promise<unknown[]> {
  const response = await fetcher(new URL(path, `${config.url}/`), {
    ...init,
    signal,
    cache: "no-cache",
    headers: {
      apikey: config.key,
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok)
    throw new Error(`Hosted search request failed (${response.status})`);
  const value: unknown = await response.json();
  if (!Array.isArray(value)) throw new Error("Hosted search returned an invalid shape");
  return value;
}

function daySummary(value: unknown): DailySummary | null {
  if (
    !isRecord(value) ||
    !isString(value.date) ||
    !DAY_VALUE.test(value.date) ||
    !isString(value.generated_at) ||
    typeof value.complete !== "boolean" ||
    !["source_total", "fetched_count", "relevant_count", "shortlist_count"].every(
      (key) => isNumber(value[key]),
    )
  ) {
    return null;
  }
  return {
    date: value.date,
    generated_at: value.generated_at,
    source_total: Number(value.source_total),
    fetched_count: Number(value.fetched_count),
    relevant_count: Number(value.relevant_count),
    shortlist_count: Number(value.shortlist_count),
    complete: value.complete,
    path: `/data/feed/${value.date}.json`,
  };
}

function mapPaper(value: unknown): DailyPaper | null {
  if (!isRecord(value) || !isString(value.paper_id)) return null;
  const paper: unknown = {
    id: value.paper_id,
    url: value.url,
    title: value.title,
    abstract: value.abstract,
    authors: value.authors,
    categories: value.categories,
    primary_category: value.primary_category,
    published: value.published,
    updated: value.updated,
    comment: value.comment,
    relevance: {
      relevant: true,
      lane: value.lane,
      score: value.relevance_score,
      reasons: value.relevance_reasons,
      strong_hits: value.strong_hits,
      support_hits: value.support_hits,
    },
    interest: { score: value.interest_score, reasons: value.interest_reasons },
    topics: value.topics,
    tricks: value.tricks,
  };
  return isDailyPaper(paper) ? paper : null;
}

export async function fetchHostedIndex(
  config: HostedConfig,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<DailyIndex> {
  const rows = await requestRows(
    config,
    `rest/v1/feed_days?select=${DAY_SELECT}&complete=eq.true&order=date.desc&limit=366`,
    signal,
    fetcher,
  );
  const days = rows.map(daySummary);
  if (days.some((day) => day === null)) throw new Error("Hosted day index is invalid");
  const index: unknown = {
    schema_version: 1,
    generated_at: days[0]?.generated_at ?? new Date(0).toISOString(),
    days,
  };
  if (!isFeedIndex(index)) throw new Error("Hosted day index is invalid");
  return index;
}

export async function fetchHostedDay(
  config: HostedConfig,
  selected: string,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<DailyDay> {
  if (!DAY_VALUE.test(selected)) throw new Error("Hosted day value is invalid");
  const [days, papers] = await Promise.all([
    requestRows(
      config,
      `rest/v1/feed_days?select=${DAY_SELECT}&date=eq.${selected}&complete=eq.true&limit=1`,
      signal,
      fetcher,
    ),
    requestRows(
      config,
      `rest/v1/feed_papers?select=${PAPER_SELECT}&date=eq.${selected}&order=position.asc`,
      signal,
      fetcher,
    ),
  ]);
  const row = days[0];
  if (!isRecord(row)) throw new Error("Hosted day was not found");
  const mapped = papers.map(mapPaper);
  if (mapped.some((paper) => paper === null))
    throw new Error("Hosted papers are invalid");
  const shortlistIds = papers
    .filter((paper) => isRecord(paper) && paper.shortlisted === true)
    .map((paper) => (isRecord(paper) ? paper.paper_id : ""));
  const day: unknown = {
    schema_version: 1,
    policy_version: row.policy_version,
    date: row.date,
    generated_at: row.generated_at,
    source: {
      provider: "arXiv",
      query: row.query,
      timezone: "UTC",
      complete: row.complete,
      source_total: row.source_total,
      fetched_count: row.fetched_count,
      unique_count: row.unique_count,
      page_count: row.page_count,
    },
    relevant_count: row.relevant_count,
    shortlist_count: row.shortlist_count,
    shortlist_ids: shortlistIds,
    papers: mapped,
  };
  if (!isFeedDay(day)) throw new Error("Hosted day is invalid");
  return day;
}

export async function searchHostedFeed(
  config: HostedConfig,
  options: SearchOptions,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<HostedResult> {
  const rows = await requestRows(config, "rest/v1/rpc/search_feed", signal, fetcher, {
    method: "POST",
    body: JSON.stringify({
      search_query: options.query,
      lane_filter: options.lane ?? null,
      shortlist_only: options.shortlist,
      page_size: options.limit,
      page_offset: options.offset,
    }),
  });
  const papers: HostedPaper[] = rows.map((row) => {
    const paper = mapPaper(row);
    if (
      !paper ||
      !isRecord(row) ||
      !isString(row.date) ||
      !DAY_VALUE.test(row.date) ||
      typeof row.shortlisted !== "boolean" ||
      !isNumber(row.rank)
    ) {
      throw new Error("Hosted search paper is invalid");
    }
    return { ...paper, date: row.date, shortlisted: row.shortlisted, rank: row.rank };
  });
  const total =
    rows.length && isRecord(rows[0]) && isNumber(rows[0].total_count)
      ? Number(rows[0].total_count)
      : 0;
  return { papers, total, limit: options.limit, offset: options.offset };
}

export async function searchHostedCorpus(
  config: HostedConfig,
  query: string,
  limit: number,
  offset: number,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<CorpusResult> {
  const rows = await requestRows(config, "rest/v1/rpc/search_corpus", signal, fetcher, {
    method: "POST",
    body: JSON.stringify({
      search_query: query,
      page_size: limit,
      page_offset: offset,
    }),
  });
  const matches: CorpusMatch[] = rows.map((row) => {
    if (
      !isRecord(row) ||
      !isString(row.paper_id) ||
      !isNumber(row.rank) ||
      !isNumber(row.total_count)
    ) {
      throw new Error("Hosted corpus result is invalid");
    }
    return { paperId: row.paper_id, rank: row.rank };
  });
  const total =
    rows.length && isRecord(rows[0]) && isNumber(rows[0].total_count)
      ? Number(rows[0].total_count)
      : 0;
  return { matches, total, limit, offset };
}
