import type { FullReading } from "../types";
import {
  hasFilledFields,
  hasOnlyKeys,
  isFilledString,
  isNumber,
  isPrimaryUrl,
  isRecord,
  isString,
  isStringArray,
  isWebUrl,
} from "./guards";

const READING_KEYS = new Set([
  "stable_id",
  "reading_depth",
  "source_provenance",
  "question",
  "key_findings",
  "method",
  "techniques",
  "evaluations",
  "limitations",
  "failure_modes",
  "reusable_insights",
  "open_questions",
  "competitive_landscape",
  "novelty_assessment",
  "verification",
  "confidence",
  "reviewer_notes",
]);
const PROVENANCE_KEYS = new Set([
  "source_locator",
  "pdf_sha256",
  "source_format",
  "source_sha256",
  "text_sha256",
  "page_count",
  "extracted_at",
  "review_pass",
]);
const FINDING_KEYS = new Set(["claim", "evidence", "attribution", "anchors"]);
const ANCHOR_KEYS = new Set(["page", "section"]);
const METHOD_KEYS = new Set(["core_idea", "mechanism", "assumptions"]);
const TECHNIQUE_KEYS = new Set(["id", "role"]);
const EVALUATION_KEYS = new Set(["setting", "metric", "result", "baseline"]);
const COMPETITOR_KEYS = new Set([
  "canonical_id",
  "title",
  "url",
  "relationship",
  "difference",
  "source_kind",
  "checked_at",
  "source_version",
]);
const NOVELTY_KEYS = new Set(["author_claim", "evidence", "reviewer_inference"]);
const VERIFICATION_KEYS = new Set([
  "reviewer_id",
  "checked_at",
  "passage_check",
  "competitor_check",
]);

function isNovelty(value: unknown): boolean {
  return (
    isFilledString(value) ||
    (isRecord(value) &&
      hasOnlyKeys(value, NOVELTY_KEYS) &&
      isFilledString(value.author_claim) &&
      isFilledString(value.reviewer_inference) &&
      (value.evidence == null || isString(value.evidence)))
  );
}

function isCompetitor(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, COMPETITOR_KEYS)) return false;
  return (
    ["canonical_id", "title", "url", "relationship", "difference"].every((key) =>
      isFilledString(value[key]),
    ) &&
    isPrimaryUrl(value.url) &&
    (!("source_kind" in value) ||
      ["arxiv", "openreview", "official-proceedings", "publisher"].includes(
        String(value.source_kind),
      )) &&
    (!("checked_at" in value) || isFilledString(value.checked_at)) &&
    (!("source_version" in value) || isFilledString(value.source_version))
  );
}

function isVerification(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, VERIFICATION_KEYS) &&
    hasFilledFields(value, [
      "reviewer_id",
      "checked_at",
      "passage_check",
      "competitor_check",
    ])
  );
}

function hasReadingShape(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, READING_KEYS)) return false;
  const provenance = value.source_provenance;
  const method = value.method;
  const findings = value.key_findings;
  const competitors = value.competitive_landscape;
  if (!isRecord(provenance) || !isRecord(method)) return false;
  const pageCount = provenance.page_count;
  const depth = String(value.reading_depth);
  const pdfSource =
    !("source_format" in provenance) &&
    !("source_sha256" in provenance) &&
    /^[0-9a-f]{64}$/.test(String(provenance.pdf_sha256));
  const htmlSource =
    !("pdf_sha256" in provenance) &&
    provenance.source_format === "html" &&
    /^[0-9a-f]{64}$/.test(String(provenance.source_sha256));
  const baseIsValid =
    isFilledString(value.stable_id) &&
    ["full_text", "verified"].includes(depth) &&
    hasOnlyKeys(provenance, PROVENANCE_KEYS) &&
    hasFilledFields(provenance, [
      "source_locator",
      "text_sha256",
      "extracted_at",
      "review_pass",
    ]) &&
    isWebUrl(provenance.source_locator) &&
    (pdfSource || htmlSource) &&
    /^[0-9a-f]{64}$/.test(provenance.text_sha256 as string) &&
    isNumber(pageCount) &&
    Number.isInteger(pageCount) &&
    pageCount >= 1 &&
    ["primary-full-text-v1", "secondary-verified-v1"].includes(
      String(provenance.review_pass),
    ) &&
    isFilledString(value.question) &&
    Array.isArray(findings) &&
    findings.length > 0 &&
    findings.every(
      (finding) =>
        isRecord(finding) &&
        hasOnlyKeys(finding, FINDING_KEYS) &&
        isFilledString(finding.claim) &&
        isFilledString(finding.evidence) &&
        (!("attribution" in finding) ||
          ["author-reported", "reviewer-inference", "contradiction-audit"].includes(
            String(finding.attribution),
          )) &&
        Array.isArray(finding.anchors) &&
        finding.anchors.length > 0 &&
        finding.anchors.every(
          (anchor) =>
            isRecord(anchor) &&
            hasOnlyKeys(anchor, ANCHOR_KEYS) &&
            isNumber(anchor.page) &&
            Number.isInteger(anchor.page) &&
            anchor.page >= 1 &&
            anchor.page <= pageCount &&
            isFilledString(anchor.section),
        ),
    ) &&
    hasOnlyKeys(method, METHOD_KEYS) &&
    hasFilledFields(method, ["core_idea", "mechanism"]) &&
    isStringArray(method.assumptions) &&
    method.assumptions.every(isFilledString) &&
    Array.isArray(value.techniques) &&
    value.techniques.every(
      (technique) =>
        isRecord(technique) &&
        hasOnlyKeys(technique, TECHNIQUE_KEYS) &&
        hasFilledFields(technique, ["id", "role"]),
    ) &&
    Array.isArray(value.evaluations) &&
    value.evaluations.every(
      (evaluation) =>
        isRecord(evaluation) &&
        hasOnlyKeys(evaluation, EVALUATION_KEYS) &&
        hasFilledFields(evaluation, ["setting", "metric", "result", "baseline"]),
    ) &&
    ["limitations", "failure_modes", "reusable_insights", "open_questions"].every(
      (key) => isStringArray(value[key]) && value[key].every(isFilledString),
    ) &&
    Array.isArray(competitors) &&
    competitors.length >= 3 &&
    competitors.every(isCompetitor) &&
    new Set(competitors.map((competitor) => competitor.canonical_id)).size ===
      competitors.length &&
    competitors.every((competitor) => competitor.canonical_id !== value.stable_id) &&
    isNovelty(value.novelty_assessment) &&
    (!("verification" in value) || isVerification(value.verification)) &&
    isNumber(value.confidence) &&
    value.confidence >= 0 &&
    value.confidence <= 1 &&
    isFilledString(value.reviewer_notes);
  if (!baseIsValid) return false;
  if (depth === "full_text") {
    return provenance.review_pass === "primary-full-text-v1";
  }
  return (
    provenance.review_pass === "secondary-verified-v1" &&
    isVerification(value.verification) &&
    isRecord(value.novelty_assessment) &&
    findings.every(
      (finding) =>
        isRecord(finding) &&
        ["author-reported", "reviewer-inference", "contradiction-audit"].includes(
          String(finding.attribution),
        ),
    ) &&
    competitors.every(
      (competitor) =>
        isRecord(competitor) &&
        ["arxiv", "openreview", "official-proceedings", "publisher"].includes(
          String(competitor.source_kind),
        ) &&
        isFilledString(competitor.checked_at) &&
        isFilledString(competitor.source_version),
    )
  );
}

export type FullReadingExpectation = {
  stableId: string;
  readingDepth: FullReading["reading_depth"];
};

export function readingError(
  value: unknown,
  expected?: FullReadingExpectation,
): string | null {
  if (!hasReadingShape(value)) return "invalid full reading contract";
  const reading = value as FullReading;
  if (expected && reading.stable_id !== expected.stableId) {
    return "full reading ID mismatch";
  }
  if (expected && reading.reading_depth !== expected.readingDepth) {
    return "full reading depth mismatch";
  }
  return null;
}

export function isReadingPayload(
  value: unknown,
  expected?: FullReadingExpectation,
): value is FullReading {
  return readingError(value, expected) === null;
}
