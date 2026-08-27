import type { Atlas } from "../types";
import {
  type RecordValue,
  hasStringFields,
  isNumber,
  isNumberRecord,
  isRecord,
  isString,
  isStringArray,
  isWebUrl,
} from "./guards";
import { isIdea, portfolioError } from "./idea";
import { atlasScope, layoutError } from "./semantic";

export { isReadingPayload, readingError } from "./reading";
export type { FullReadingExpectation } from "./reading";

const READING_PATH =
  /^\/data\/readings\/[a-z0-9][a-z0-9-]{0,71}--[0-9a-f]{12}-[0-9a-f]{12}\.json$/;

function isRoute(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isNumber(value.score) &&
    isStringArray(value.evidence)
  );
}

function isReading(value: unknown): boolean {
  return (
    isRecord(value) &&
    ["problem", "approach", "evidence", "limitations", "why_it_matters"].every((key) =>
      isString(value[key]),
    )
  );
}

function paperError(value: unknown): string | null {
  if (!isRecord(value)) return "not an object";
  if (!isString(value.id)) return "missing ID";
  if (!isNumber(value.collection_id)) return "invalid collection ID";
  if (!["paper", "non_paper_context"].includes(String(value.record_kind))) {
    return "invalid record kind";
  }
  if (
    !isString(value.title) ||
    !isWebUrl(value.url) ||
    !isWebUrl(value.collection_url) ||
    !isString(value.source)
  ) {
    return "invalid bibliographic fields";
  }
  if (
    (value.stable_id != null && !isString(value.stable_id)) ||
    (value.published != null && !isString(value.published)) ||
    (value.note != null && !isString(value.note))
  ) {
    return "invalid optional bibliographic fields";
  }
  if (
    !["metadata", "abstract", "full_text", "verified", "context"].includes(
      String(value.reading_depth),
    )
  ) {
    return "invalid reading depth";
  }
  if (!isStringArray(value.authors) || !isStringArray(value.categories)) {
    return "invalid author or category list";
  }
  if (!Array.isArray(value.topics) || !value.topics.every(isRoute)) {
    return "invalid topic routes";
  }
  if (!Array.isArray(value.tricks) || !value.tricks.every(isRoute)) {
    return "invalid technique routes";
  }
  if (!isReading(value.reading)) return "invalid abstract reading";
  if ("full_reading" in value) return "legacy embedded reading is not allowed";
  if (
    value.full_reading_path != null &&
    (!isString(value.full_reading_path) || !READING_PATH.test(value.full_reading_path))
  ) {
    return "invalid full reading path";
  }
  if (
    value.record_kind === "non_paper_context" &&
    (value.reading_depth !== "context" || value.full_reading_path != null)
  ) {
    return "context record presented as a paper reading";
  }
  if (value.record_kind === "paper" && value.reading_depth === "context") {
    return "paper record presented as context";
  }
  if (value.record_kind === "paper") {
    const hasDepth = ["full_text", "verified"].includes(String(value.reading_depth));
    const hasPath = value.full_reading_path != null;
    if (hasDepth !== hasPath) return "reading depth and detail path disagree";
    if (hasPath && !isString(value.stable_id)) {
      return "full reading path requires a stable ID";
    }
  }
  return null;
}

function isPaper(value: unknown): boolean {
  return paperError(value) === null;
}

function isRepo(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    ["id", "name", "description", "scope"].every((key) => isString(value[key])) &&
    typeof value.ideation_enabled === "boolean" &&
    hasStringFields(value, ["relationship", "canonical_group"]) &&
    isNumberRecord(value.languages_by_loc) &&
    (value.total_loc == null || isNumber(value.total_loc)) &&
    Array.isArray(value.topics) &&
    value.topics.every(isRoute) &&
    Array.isArray(value.tricks) &&
    value.tricks.every(isRoute)
  );
}

export function isCoverage(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const access = value.source_access;
  const accessIsValid =
    isRecord(access) &&
    [
      "canonical_records_classified",
      "paper_records",
      "non_paper_records",
      "adapter_supported",
      "adapter_missing",
      "supported_records_without_readings",
    ].every((key) => isNumber(access[key])) &&
    isNumberRecord(access.by_route) &&
    isNumberRecord(access.by_extraction_status);
  return (
    isString(value.updated_at) &&
    [
      "collection_entries",
      "canonical_records",
      "abstract_entries",
      "fulltext_extracted",
      "full_readings",
      "competitive_landscapes",
      "canonical_paper_fulltext_extraction_coverage",
      "canonical_paper_full_reading_coverage",
    ].every((key) => isNumber(value[key])) &&
    isNumberRecord(value.entry_reading_depth) &&
    Array.isArray(value.extraction_failures) &&
    value.extraction_failures.every(isRecord) &&
    accessIsValid &&
    !("social_sources" in value) &&
    isRecord(value.completion_gate) &&
    typeof value.completion_gate.satisfied === "boolean" &&
    isString(value.completion_gate.rule)
  );
}

export function isTaxon(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.label) &&
    isNumber(value.paper_count)
  );
}

function itemError(
  topics: unknown[],
  tricks: unknown[],
  papers: unknown[],
  repos: unknown[],
  ideas: unknown[],
): string | null {
  const invalidTopic = topics.findIndex((item) => !isTaxon(item));
  if (invalidTopic >= 0) return `invalid topic at index ${invalidTopic}`;
  const invalidTrick = tricks.findIndex((item) => !isTaxon(item));
  if (invalidTrick >= 0) return `invalid technique at index ${invalidTrick}`;
  const invalidPaper = papers.findIndex((item) => !isPaper(item));
  if (invalidPaper >= 0) {
    return `invalid paper at index ${invalidPaper}: ${paperError(papers[invalidPaper])}`;
  }
  const invalidRepo = repos.findIndex((item) => !isRepo(item));
  if (invalidRepo >= 0) return `invalid repository at index ${invalidRepo}`;
  const fullReadingIds = new Set(
    papers.flatMap((paper) => {
      if (
        !isRecord(paper) ||
        !["full_text", "verified"].includes(String(paper.reading_depth)) ||
        !isString(paper.stable_id)
      ) {
        return [];
      }
      return [paper.stable_id];
    }),
  );
  const invalidIdea = ideas.findIndex((item) => !isIdea(item, fullReadingIds));
  if (invalidIdea >= 0) return `invalid idea at index ${invalidIdea}`;
  return null;
}

function referenceError(
  topics: unknown[],
  tricks: unknown[],
  papers: unknown[],
  repos: unknown[],
  ideas: unknown[],
): string | null {
  const ideaIds = ideas.map((idea) => (isRecord(idea) ? idea.id : null));
  if (new Set(ideaIds).size !== ideaIds.length) return "duplicate idea IDs";
  const hierarchyError = portfolioError(ideas);
  if (hierarchyError) return hierarchyError;
  const graphIds = [
    ...topics.map((topic) => `topic:${String((topic as RecordValue).id)}`),
    ...tricks.map((trick) => `trick:${String((trick as RecordValue).id)}`),
    ...papers.map((paper) => String((paper as RecordValue).id)),
    ...repos.map((repo) => String((repo as RecordValue).id)),
    ...ideas.map((idea) => String((idea as RecordValue).id)),
  ];
  if (new Set(graphIds).size !== graphIds.length) return "duplicate graph node IDs";

  const topicIds = new Set(topics.map((item) => String((item as RecordValue).id)));
  const trickIds = new Set(tricks.map((item) => String((item as RecordValue).id)));
  const repoIds = new Set(repos.map((item) => String((item as RecordValue).id)));
  const unknownPaperTopic = papers.findIndex(
    (paper) =>
      isRecord(paper) &&
      Array.isArray(paper.topics) &&
      paper.topics.some((route) => isRecord(route) && !topicIds.has(String(route.id))),
  );
  if (unknownPaperTopic >= 0) {
    return `unknown paper topic reference at index ${unknownPaperTopic}`;
  }
  const unknownPaperTrick = papers.findIndex(
    (paper) =>
      isRecord(paper) &&
      Array.isArray(paper.tricks) &&
      paper.tricks.some((route) => isRecord(route) && !trickIds.has(String(route.id))),
  );
  if (unknownPaperTrick >= 0) {
    return `unknown paper technique reference at index ${unknownPaperTrick}`;
  }
  const unknownIdeaTopic = ideas.findIndex(
    (idea) =>
      isRecord(idea) &&
      Array.isArray(idea.topic_ids) &&
      idea.topic_ids.some((id) => isString(id) && !topicIds.has(id)),
  );
  if (unknownIdeaTopic >= 0) {
    return `unknown idea topic reference at index ${unknownIdeaTopic}`;
  }
  const unknownIdeaTrick = ideas.findIndex(
    (idea) =>
      isRecord(idea) &&
      Array.isArray(idea.trick_ids) &&
      idea.trick_ids.some((id) => isString(id) && !trickIds.has(id)),
  );
  if (unknownIdeaTrick >= 0) {
    return `unknown idea technique reference at index ${unknownIdeaTrick}`;
  }
  const unknownIdeaRepo = ideas.findIndex(
    (idea) =>
      isRecord(idea) &&
      Array.isArray(idea.repo_ids) &&
      idea.repo_ids.some((id) => isString(id) && !repoIds.has(id)),
  );
  if (unknownIdeaRepo >= 0) {
    return `unknown idea repository reference at index ${unknownIdeaRepo}`;
  }
  const paperIds = new Set<string>();
  for (const paper of papers) {
    if (!isRecord(paper)) continue;
    if (isString(paper.id)) paperIds.add(paper.id);
    if (isString(paper.stable_id)) paperIds.add(paper.stable_id);
  }
  const missingPaper = ideas.findIndex(
    (idea) =>
      isRecord(idea) &&
      isRecord(idea.brief) &&
      Array.isArray(idea.brief.paper_ids) &&
      idea.brief.paper_ids.some((id) => isString(id) && !paperIds.has(id)),
  );
  return missingPaper >= 0
    ? `unresolved idea paper reference at index ${missingPaper}`
    : null;
}

function countError(
  meta: RecordValue,
  coverage: RecordValue,
  papers: unknown[],
  repos: unknown[],
  ideas: unknown[],
): string | null {
  const researchCount = papers.filter(
    (item) => isRecord(item) && item.record_kind === "paper",
  ).length;
  const readingIds = new Set(
    papers
      .filter((paper) => isRecord(paper) && isString(paper.full_reading_path))
      .map((paper) => String((paper as RecordValue).stable_id)),
  );
  return meta.paper_count !== papers.length ||
    meta.research_entry_count !== researchCount ||
    meta.context_entry_count !== papers.length - researchCount ||
    meta.repo_count !== repos.length ||
    meta.idea_count !== ideas.length ||
    meta.full_reading_count !== readingIds.size ||
    meta.full_reading_count !== coverage.full_readings ||
    meta.extracted_fulltext_count !== coverage.fulltext_extracted
    ? "inconsistent atlas counts"
    : null;
}

function repoError(
  meta: RecordValue,
  repos: unknown[],
  ideas: unknown[],
): string | null {
  const hasIdeaRefs = ideas.some(
    (idea) =>
      isRecord(idea) &&
      ((Array.isArray(idea.repo_ids) && idea.repo_ids.length > 0) ||
        (isRecord(idea.brief) &&
          Array.isArray(idea.brief.repo_ids) &&
          idea.brief.repo_ids.length > 0)),
  );
  return meta.repo_count !== 0 || repos.length > 0 || hasIdeaRefs
    ? "repository data is not allowed"
    : null;
}

export function atlasValidationError(value: unknown): string | null {
  if (!isRecord(value) || !isRecord(value.meta)) return "missing atlas metadata";
  if ("personal_sources" in value) return "personal source data is not allowed";
  if (
    !isString(value.meta.generated_at) ||
    !isNumber(value.meta.paper_count) ||
    !isNumber(value.meta.research_entry_count) ||
    !isNumber(value.meta.context_entry_count) ||
    !isNumber(value.meta.repo_count) ||
    !isNumber(value.meta.idea_count) ||
    !isNumber(value.meta.full_reading_count) ||
    !isNumber(value.meta.extracted_fulltext_count) ||
    !isString(value.meta.notice) ||
    !Array.isArray(value.topics) ||
    !Array.isArray(value.tricks) ||
    !Array.isArray(value.papers) ||
    !Array.isArray(value.repos) ||
    !Array.isArray(value.ideas) ||
    (value.layout != null && !isRecord(value.layout)) ||
    (value.idea_layout != null && !isRecord(value.idea_layout)) ||
    !isCoverage(value.coverage)
  ) {
    return "invalid top-level atlas contract";
  }
  const coverage = value.coverage as RecordValue;
  const repositories = repoError(value.meta, value.repos, value.ideas);
  if (repositories) return repositories;
  const items = itemError(
    value.topics,
    value.tricks,
    value.papers,
    value.repos,
    value.ideas,
  );
  if (items) return items;
  if (value.layout != null) {
    const typed = value as unknown as Atlas;
    const scope = atlasScope(typed);
    const semanticError = layoutError(value.layout, scope);
    if (semanticError) return semanticError;
  }
  const references = referenceError(
    value.topics,
    value.tricks,
    value.papers,
    value.repos,
    value.ideas,
  );
  if (references) return references;
  const counts = countError(
    value.meta,
    coverage,
    value.papers,
    value.repos,
    value.ideas,
  );
  return counts;
}

export function isAtlasPayload(value: unknown): value is Atlas {
  return atlasValidationError(value) === null;
}
