import type {
  DailyDay,
  DailyIndex,
  DailyPaper,
  DailyRelevance,
  DailySource,
  DailySummary,
  Route,
} from "../types";
import { isNumber, isRecord, isString, isStringArray, isWebUrl } from "./guards";
import { basePath } from "./paths";

const DAY_PATH = /^\/data\/feed\/\d{4}-\d{2}-\d{2}\.json$/;
const DAY_VALUE = /^\d{4}-\d{2}-\d{2}$/;

function isRoute(value: unknown): value is Route {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isNumber(value.score) &&
    isStringArray(value.evidence)
  );
}

function isScore(value: unknown): boolean {
  return isRecord(value) && isNumber(value.score) && isStringArray(value.reasons);
}

function isRelevance(value: unknown): value is DailyRelevance {
  if (!isRecord(value)) return false;
  return (
    isScore(value) &&
    typeof value.relevant === "boolean" &&
    ["core", "field", "math-stat", "adjacent"].includes(String(value.lane)) &&
    isStringArray(value.strong_hits) &&
    isStringArray(value.support_hits)
  );
}

export function isDailyPaper(value: unknown): value is DailyPaper {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isWebUrl(value.url) &&
    ["title", "abstract", "primary_category", "published", "updated", "comment"].every(
      (key) => isString(value[key]),
    ) &&
    isStringArray(value.authors) &&
    isStringArray(value.categories) &&
    isRelevance(value.relevance) &&
    isScore(value.interest) &&
    Array.isArray(value.topics) &&
    value.topics.every(isRoute) &&
    Array.isArray(value.tricks) &&
    value.tricks.every(isRoute)
  );
}

function isSource(value: unknown): value is DailySource {
  return (
    isRecord(value) &&
    value.provider === "arXiv" &&
    value.timezone === "UTC" &&
    isString(value.query) &&
    typeof value.complete === "boolean" &&
    ["source_total", "fetched_count", "unique_count", "page_count"].every((key) =>
      isNumber(value[key]),
    )
  );
}

function isSummary(value: unknown): value is DailySummary {
  return (
    isRecord(value) &&
    isString(value.date) &&
    DAY_VALUE.test(value.date) &&
    isString(value.generated_at) &&
    ["source_total", "fetched_count", "relevant_count", "shortlist_count"].every(
      (key) => isNumber(value[key]),
    ) &&
    typeof value.complete === "boolean" &&
    isString(value.path) &&
    DAY_PATH.test(value.path)
  );
}

export function isFeedIndex(value: unknown): value is DailyIndex {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    isString(value.generated_at) &&
    Array.isArray(value.days) &&
    value.days.every(isSummary)
  );
}

export function isFeedDay(value: unknown): value is DailyDay {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    !isString(value.policy_version) ||
    !isString(value.date) ||
    !DAY_VALUE.test(value.date) ||
    !isString(value.generated_at) ||
    !isSource(value.source) ||
    !isNumber(value.relevant_count) ||
    !isNumber(value.shortlist_count) ||
    !isStringArray(value.shortlist_ids) ||
    !Array.isArray(value.papers) ||
    !value.papers.every(isDailyPaper)
  ) {
    return false;
  }
  const paperIds = new Set(value.papers.map((paper) => paper.id));
  return (
    value.papers.length === value.relevant_count &&
    value.shortlist_ids.length === value.shortlist_count &&
    value.shortlist_ids.every((id) => paperIds.has(id)) &&
    value.source.complete &&
    value.source.fetched_count === value.source.source_total
  );
}

async function fetchJson(
  path: string,
  signal: AbortSignal,
  fetcher: typeof fetch,
  base?: string,
): Promise<unknown> {
  const response = await fetcher(basePath(path, base), {
    signal,
    cache: "no-cache",
  });
  if (!response.ok) throw new Error(`Daily feed request failed (${response.status})`);
  return response.json();
}

export async function fetchFeedIndex(
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<DailyIndex> {
  const value = await fetchJson("/data/feed/index.json", signal, fetcher, base);
  if (!isFeedIndex(value)) throw new Error("Daily feed index has an invalid shape");
  return value;
}

export async function fetchFeedDay(
  path: string,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<DailyDay> {
  if (!DAY_PATH.test(path)) throw new Error("Daily feed path is invalid");
  const value = await fetchJson(path, signal, fetcher, base);
  if (!isFeedDay(value)) throw new Error("Daily feed day has an invalid shape");
  return value;
}
