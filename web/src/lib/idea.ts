import {
  type RecordValue,
  hasFilledFields,
  hasOnlyKeys,
  hasStringFields,
  isFilledArray,
  isFilledString,
  isIsoDate,
  isNumber,
  isPrimaryUrl,
  isRecord,
  isString,
  isStringArray,
  optionalFilled,
} from "./guards";

const BRIEF_KEYS = new Set([
  "title",
  "thesis",
  "motivation",
  "research_question",
  "method",
  "evaluation",
  "risks",
  "first_week",
  "paper_ids",
  "repo_ids",
  "confidence",
  "status",
  "evidence_note",
  "non_claims",
  "subquestions",
  "generation_routes",
  "core_design",
  "what_counts_as_learning_signal",
  "validation_funnel",
  "human_in_the_loop",
  "scaling_claim_protocol",
  "experiment",
  "reading_roles",
  "route_dictionary_protocol",
  "milestones",
  "falsifiers",
  "competitive_landscape",
  "novelty_assessment",
]);
const EXPERIMENT_KEYS = new Set([
  "primary_hypothesis",
  "secondary_hypothesis",
  "domains",
  "baselines",
  "ablations",
  "primary_outcome",
  "analysis",
  "claim_hierarchy",
  "selection_protocol",
  "resource_scalarization",
  "action_ontology",
  "decision_rule",
]);
const ROLE_KEYS = new Set(["paper_id", "role", "use"]);
const ROUTE_KEYS = new Set([
  "shared_axes",
  "markov_family",
  "regression_family",
  "freeze_boundary",
  "invalidation_rules",
]);
const MILESTONE_KEYS = new Set(["name", "deliverable", "pass_condition"]);
const GENERATION_KEYS = new Set(["route", "mechanism", "examples", "best_when"]);
const DESIGN_KEYS = new Set([
  "unit_of_search",
  "generator",
  "fitness",
  "selection",
  "critical_control",
]);
const SIGNAL_KEYS = new Set(["answer", "evidence_hierarchy", "recommended_statistics"]);
const LEVEL_KEYS = new Set(["level", "name", "evidence", "does_not_show"]);
const HUMAN_KEYS = new Set([
  "answer",
  "short_answer",
  "policy",
  "routing_policy",
  "measurement",
  "humans_not_needed_for",
  "humans_needed_for",
]);
const SCALE_KEYS = new Set([
  "answer",
  "short_answer",
  "minimum_design",
  "prospective_design",
  "supporting_evidence",
  "claim_blockers",
  "why_small_models_fail",
  "claim_language",
]);
const COMPETITOR_KEYS = new Set([
  "canonical_id",
  "title",
  "url",
  "relationship",
  "difference",
  "source_kind",
  "checked_at",
  "source_version",
  "source_date",
  "provenance_status",
]);
const FACTOR_KEYS = new Set(["id", "score", "max", "rationale"]);
const FEASIBILITY_KEYS = new Set([
  "score",
  "band",
  "screening_estimate",
  "factors",
  "assumptions",
  "version",
]);
const FACTOR_MAXIMA: Readonly<Record<string, number>> = {
  implementation_leverage: 2.5,
  compute_and_data: 2.5,
  evaluation_clarity: 2,
  novelty_risk: 1.5,
  time_to_signal: 1.5,
};
const PROVISIONAL_CAPS: Readonly<Record<string, number>> = {
  evaluation_clarity: 0.9,
  novelty_risk: 0.3,
};

function isCompetitor(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, COMPETITOR_KEYS)) return false;
  const status = value.provenance_status;
  const commonIsValid =
    ["canonical_id", "title", "url", "relationship", "difference"].every((key) =>
      isFilledString(value[key]),
    ) &&
    isPrimaryUrl(value.url) &&
    ["arxiv", "openreview", "official-proceedings", "publisher"].includes(
      String(value.source_kind),
    ) &&
    isIsoDate(value.checked_at);
  if (!commonIsValid) return false;
  if (status === "version-verified") {
    return (
      isFilledString(value.source_version) &&
      isIsoDate(value.source_date) &&
      value.source_date <= String(value.checked_at)
    );
  }
  if (status === "legacy-unversioned") {
    return value.source_version == null && value.source_date == null;
  }
  return false;
}

function isCompetitorPanel(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every(isCompetitor) &&
    new Set(
      value.map((competitor) =>
        isRecord(competitor) ? competitor.canonical_id : undefined,
      ),
    ).size === value.length
  );
}

function isGenerationRoute(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, GENERATION_KEYS) &&
    hasFilledFields(value, ["route", "mechanism", "examples", "best_when"])
  );
}

function isCoreDesign(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, DESIGN_KEYS) &&
    hasFilledFields(value, [
      "unit_of_search",
      "generator",
      "selection",
      "critical_control",
    ]) &&
    isFilledArray(value.fitness)
  );
}

function isLearningSignal(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, SIGNAL_KEYS) ||
    !isFilledString(value.answer) ||
    !isFilledArray(value.recommended_statistics) ||
    !Array.isArray(value.evidence_hierarchy) ||
    value.evidence_hierarchy.length === 0
  ) {
    return false;
  }
  const levels = value.evidence_hierarchy;
  return (
    levels.every(
      (level) =>
        isRecord(level) &&
        hasOnlyKeys(level, LEVEL_KEYS) &&
        isNumber(level.level) &&
        Number.isInteger(level.level) &&
        level.level > 0 &&
        hasFilledFields(level, ["name", "evidence", "does_not_show"]),
    ) &&
    new Set(levels.map((level) => (isRecord(level) ? level.level : null))).size ===
      levels.length
  );
}

function isValidationStage(value: unknown): boolean {
  return isRecord(value) && hasFilledFields(value, ["stage", "cost", "gate"]);
}

function usesHumanLoop(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, HUMAN_KEYS)) return false;
  const hasDecision = [value.answer, value.short_answer].some(isFilledString);
  return (
    hasDecision &&
    isFilledString(value.measurement) &&
    isFilledArray(value.humans_not_needed_for) &&
    isFilledArray(value.humans_needed_for) &&
    ["answer", "short_answer", "policy", "routing_policy"].every(
      (field) => !(field in value) || isFilledString(value[field]),
    )
  );
}

function isScalingProtocol(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, SCALE_KEYS)) return false;
  const hasDecision = [value.answer, value.short_answer].some(isFilledString);
  return (
    hasDecision &&
    isFilledArray(value.supporting_evidence) &&
    isFilledArray(value.claim_blockers) &&
    ["answer", "short_answer", "minimum_design", "claim_language"].every(
      (field) => !(field in value) || isFilledString(value[field]),
    ) &&
    ["prospective_design", "why_small_models_fail"].every(
      (field) => !(field in value) || isFilledArray(value[field]),
    )
  );
}

function isExperiment(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, EXPERIMENT_KEYS) &&
    hasStringFields(value, [
      "primary_hypothesis",
      "secondary_hypothesis",
      "decision_rule",
    ]) &&
    ["domains", "baselines", "ablations"].every((field) =>
      isFilledArray(value[field]),
    ) &&
    [
      value.primary_outcome,
      value.analysis,
      value.claim_hierarchy,
      value.selection_protocol,
      value.resource_scalarization,
      value.action_ontology,
    ].every(optionalFilled)
  );
}

function isReadingRole(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, ROLE_KEYS) &&
    hasFilledFields(value, ["paper_id", "role", "use"])
  );
}

function isRouteProtocol(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, ROUTE_KEYS) &&
    isFilledArray(value.shared_axes) &&
    isFilledArray(value.markov_family) &&
    isFilledArray(value.regression_family) &&
    isFilledString(value.freeze_boundary) &&
    isFilledArray(value.invalidation_rules)
  );
}

function isMilestone(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, MILESTONE_KEYS) &&
    hasFilledFields(value, ["name", "deliverable", "pass_condition"])
  );
}

function rolesMatchIds(brief: RecordValue): boolean {
  if (brief.reading_roles == null) return true;
  const paperIds = brief.paper_ids;
  if (!Array.isArray(brief.reading_roles) || !isStringArray(paperIds)) return false;
  if (!brief.reading_roles.every(isReadingRole)) return false;
  const roleIds = brief.reading_roles.map((role) => String(role.paper_id));
  return (
    new Set(roleIds).size === roleIds.length &&
    roleIds.length === paperIds.length &&
    roleIds.every((paperId) => paperIds.includes(paperId))
  );
}

type FactorValue = RecordValue & {
  id: string;
  score: number;
  max: number;
  rationale: string;
};

function isFactor(value: unknown): value is FactorValue {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, FACTOR_KEYS) &&
    isFilledString(value.id) &&
    isNumber(value.score) &&
    value.score >= 0 &&
    isNumber(value.max) &&
    value.max > 0 &&
    isFilledString(value.rationale)
  );
}

function roundDecimal(value: number): number {
  return Math.round((value + Number.EPSILON) * 10) / 10;
}

function isFeasibility(value: unknown, status: string): boolean {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, FEASIBILITY_KEYS) ||
    !Array.isArray(value.factors)
  ) {
    return false;
  }
  const factors = value.factors;
  if (factors.length !== 5 || !factors.every(isFactor)) return false;
  if (
    !isNumber(value.score) ||
    value.score < 1 ||
    value.score > 10 ||
    roundDecimal(value.score) !== value.score ||
    !["low", "medium", "high"].includes(String(value.band)) ||
    (value.screening_estimate != null &&
      typeof value.screening_estimate !== "boolean") ||
    !isStringArray(value.assumptions) ||
    !value.assumptions.every(isFilledString) ||
    !isFilledString(value.version)
  ) {
    return false;
  }
  const factorsById = new Map(factors.map((factor) => [factor.id, factor]));
  const rubricIds = Object.keys(FACTOR_MAXIMA);
  if (
    factorsById.size !== rubricIds.length ||
    rubricIds.some((id) => {
      const factor = factorsById.get(id);
      return (
        factor == null ||
        factor.max !== FACTOR_MAXIMA[id] ||
        roundDecimal(factor.score) !== factor.score ||
        factor.score > factor.max
      );
    })
  ) {
    return false;
  }
  const factorTotal = roundDecimal(
    factors.reduce((total, factor) => total + factor.score, 0),
  );
  const expectedBand =
    value.score >= 8 ? "high" : value.score >= 5.5 ? "medium" : "low";
  const statusIsValid =
    status === "provisional"
      ? value.screening_estimate === true &&
        Object.entries(PROVISIONAL_CAPS).every(
          ([id, cap]) => (factorsById.get(id)?.score ?? Infinity) <= cap,
        )
      : value.screening_estimate !== true;
  return factorTotal === value.score && value.band === expectedBand && statusIsValid;
}

function isResearchedBrief(
  idea: RecordValue,
  brief: RecordValue,
  fullReadingIds: ReadonlySet<string>,
): boolean {
  if (brief.status !== "researched-draft") return true;
  const competitors = Array.isArray(brief.competitive_landscape)
    ? brief.competitive_landscape
    : [];
  const paperIds = isStringArray(brief.paper_ids) ? brief.paper_ids : [];
  const supportCount = paperIds.filter((paperId) => fullReadingIds.has(paperId)).length;
  const userException = idea.origin === "user-specified" && competitors.length >= 10;
  return (
    ((isFilledArray(brief.method) && isStringArray(brief.method)) ||
      isCoreDesign(brief.core_design)) &&
    isFilledArray(brief.evaluation) &&
    isFilledArray(brief.risks) &&
    isFilledArray(brief.first_week) &&
    isExperiment(brief.experiment) &&
    isRecord(brief.experiment) &&
    isFilledString(brief.experiment.primary_outcome) &&
    competitors.length >= 5 &&
    competitors.every(isCompetitor) &&
    isFilledString(brief.novelty_assessment) &&
    isRecord(idea.feasibility) &&
    idea.feasibility.screening_estimate !== true &&
    (supportCount >= 2 || userException)
  );
}

function checkIdea(
  value: unknown,
  fullReadingIds: ReadonlySet<string>,
  evidence: boolean,
): boolean {
  if (!isRecord(value) || !isRecord(value.brief) || !isRecord(value.feasibility)) {
    return false;
  }
  const brief = value.brief;
  return (
    hasOnlyKeys(brief, BRIEF_KEYS) &&
    isString(value.id) &&
    (value.kind === "research" || value.kind === "blog") &&
    ["cross-paper", "cross-paper-reviewed", "user-specified"].includes(
      String(value.origin),
    ) &&
    (value.portfolio_role == null ||
      ["program", "work-package"].includes(String(value.portfolio_role))) &&
    optionalFilled(value.parent_idea_id) &&
    (value.rank_independently == null ||
      typeof value.rank_independently === "boolean") &&
    isStringArray(value.topic_ids) &&
    isStringArray(value.trick_ids) &&
    isStringArray(value.repo_ids) &&
    ["title", "thesis", "motivation", "research_question", "evidence_note"].every(
      (key) => isString(brief[key]),
    ) &&
    ["provisional", "researched-draft"].includes(String(brief.status)) &&
    ["evaluation", "risks", "first_week", "paper_ids", "repo_ids"].every((key) =>
      isStringArray(brief[key]),
    ) &&
    (brief.method == null || isStringArray(brief.method)) &&
    optionalFilled(brief.novelty_assessment) &&
    (brief.non_claims == null || isStringArray(brief.non_claims)) &&
    (brief.subquestions == null || isStringArray(brief.subquestions)) &&
    (brief.falsifiers == null || isStringArray(brief.falsifiers)) &&
    (brief.competitive_landscape == null ||
      isCompetitorPanel(brief.competitive_landscape)) &&
    (brief.generation_routes == null ||
      (Array.isArray(brief.generation_routes) &&
        brief.generation_routes.length > 0 &&
        brief.generation_routes.every(isGenerationRoute))) &&
    (brief.core_design == null || isCoreDesign(brief.core_design)) &&
    (brief.what_counts_as_learning_signal == null ||
      isLearningSignal(brief.what_counts_as_learning_signal)) &&
    (brief.validation_funnel == null ||
      (Array.isArray(brief.validation_funnel) &&
        brief.validation_funnel.length > 0 &&
        brief.validation_funnel.every(isValidationStage))) &&
    (brief.human_in_the_loop == null || usesHumanLoop(brief.human_in_the_loop)) &&
    (brief.scaling_claim_protocol == null ||
      isScalingProtocol(brief.scaling_claim_protocol)) &&
    (brief.experiment == null || isExperiment(brief.experiment)) &&
    rolesMatchIds(brief) &&
    (brief.route_dictionary_protocol == null ||
      isRouteProtocol(brief.route_dictionary_protocol)) &&
    (brief.milestones == null ||
      (Array.isArray(brief.milestones) &&
        brief.milestones.length > 0 &&
        brief.milestones.every(isMilestone))) &&
    (!evidence || isResearchedBrief(value, brief, fullReadingIds)) &&
    isNumber(brief.confidence) &&
    brief.confidence >= 0 &&
    brief.confidence <= 1 &&
    isFeasibility(value.feasibility, String(brief.status))
  );
}

export function isIdea(
  value: unknown,
  fullReadingIds: ReadonlySet<string> = new Set(),
): boolean {
  return checkIdea(value, fullReadingIds, true);
}

export function isCoreIdea(value: unknown): boolean {
  return checkIdea(value, new Set(), false);
}

export function portfolioError(ideas: readonly unknown[]): string | null {
  const ideasById = new Map<string, RecordValue>();
  for (const value of ideas) {
    if (isRecord(value) && isString(value.id)) ideasById.set(value.id, value);
  }
  for (const [index, value] of ideas.entries()) {
    if (!isRecord(value)) continue;
    const role = value.portfolio_role;
    const parentId = value.parent_idea_id;
    const rankIndependently = value.rank_independently;
    if (role == null) {
      if (parentId != null || rankIndependently != null) {
        return `portfolio metadata without a role at idea index ${index}`;
      }
      continue;
    }
    if (role === "program") {
      if (parentId != null || rankIndependently !== true) {
        return `invalid program metadata at idea index ${index}`;
      }
      continue;
    }
    if (!isString(parentId) || rankIndependently !== false) {
      return `invalid work-package metadata at idea index ${index}`;
    }
    const parent = ideasById.get(parentId);
    if (!parent || parent.portfolio_role !== "program") {
      return `unresolved work-package parent at idea index ${index}`;
    }
  }
  return null;
}
