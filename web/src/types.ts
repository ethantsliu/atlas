import type { MixQuality } from "./layout";

export type Route = {
  id: string;
  score: number;
  evidence: string[];
};

export type Reading = {
  problem: string;
  approach: string;
  evidence: string;
  limitations: string;
  why_it_matters: string;
};

export type PaperAnchor = {
  page: number;
  section: string;
};

export type KeyFinding = {
  claim: string;
  evidence: string;
  attribution?: "author-reported" | "reviewer-inference" | "contradiction-audit";
  anchors: PaperAnchor[];
};

export type PaperMethod = {
  core_idea: string;
  mechanism: string;
  assumptions: string[];
};

export type PaperTechnique = {
  id: string;
  role: string;
};

export type PaperEvaluation = {
  setting: string;
  metric: string;
  result: string;
  baseline: string;
};

export type StructuredNoveltyAssessment = {
  author_claim: string;
  evidence?: string;
  reviewer_inference: string;
};

type ReadingSourceBase = {
  source_locator: string;
  text_sha256: string;
  page_count: number;
  extracted_at: string;
  review_pass: "primary-full-text-v1" | "secondary-verified-v1";
};

export type ReadingSourceProvenance = ReadingSourceBase &
  (
    | {
        pdf_sha256: string;
        source_format?: never;
        source_sha256?: never;
      }
    | {
        source_format: "html";
        source_sha256: string;
        pdf_sha256?: never;
      }
  );

export type ReadingVerification = {
  reviewer_id: string;
  checked_at: string;
  passage_check: string;
  competitor_check: string;
};

export type ReadingDepth =
  "metadata" | "abstract" | "full_text" | "verified" | "context";

export type FullReading = {
  stable_id: string;
  reading_depth: "full_text" | "verified";
  source_provenance: ReadingSourceProvenance;
  question: string;
  key_findings: KeyFinding[];
  method: PaperMethod;
  techniques: PaperTechnique[];
  evaluations: PaperEvaluation[];
  limitations: string[];
  failure_modes: string[];
  reusable_insights: string[];
  open_questions: string[];
  competitive_landscape: CompetingPaper[];
  novelty_assessment: string | StructuredNoveltyAssessment;
  verification?: ReadingVerification;
  confidence: number;
  reviewer_notes: string;
};

export type Paper = {
  id: string;
  stable_id?: string;
  collection_id: number;
  record_kind: "paper" | "non_paper_context";
  title: string;
  url: string;
  collection_url: string;
  source: string;
  authors: string[];
  published?: string | null;
  categories: string[];
  note?: string | null;
  reading_depth: ReadingDepth;
  topics: Route[];
  tricks: Route[];
  reading: Reading;
  full_reading_path?: string;
};

export type Repo = {
  id: string;
  name: string;
  description: string;
  languages_by_loc: Record<string, number>;
  total_loc?: number;
  topics: Route[];
  tricks: Route[];
  scope: string;
  relationship: string;
  canonical_group: string;
  ideation_enabled: boolean;
};

export type ValidationStage = {
  stage: string;
  cost: string;
  gate: string;
};

export type GenerationRoute = {
  route: string;
  mechanism: string;
  examples: string;
  best_when: string;
};

export type CoreDesign = {
  unit_of_search: string;
  generator: string;
  fitness: string[];
  selection: string;
  critical_control: string;
};

export type LearningSignalLevel = {
  level: number;
  name: string;
  evidence: string;
  does_not_show: string;
};

export type LearningSignalDefinition = {
  answer: string;
  evidence_hierarchy: LearningSignalLevel[];
  recommended_statistics: string[];
};

export type HumanInTheLoop = {
  answer?: string;
  short_answer?: string;
  policy?: string;
  routing_policy?: string;
  measurement: string;
  humans_not_needed_for?: string[];
  humans_needed_for?: string[];
};

export type ScalingClaimProtocol = {
  answer?: string;
  short_answer?: string;
  minimum_design?: string;
  prospective_design?: string[];
  supporting_evidence: string[];
  claim_blockers: string[];
  why_small_models_fail?: string[];
  claim_language?: string;
};

export type ExperimentPlan = {
  primary_hypothesis: string;
  secondary_hypothesis: string;
  domains: string[];
  baselines: string[];
  ablations: string[];
  primary_outcome?: string;
  analysis?: string;
  claim_hierarchy?: string;
  selection_protocol?: string;
  resource_scalarization?: string;
  action_ontology?: string;
  decision_rule: string;
};

export type ReadingRole = {
  paper_id: string;
  role: string;
  use: string;
};

export type RouteDictionaryProtocol = {
  shared_axes: string[];
  markov_family: string[];
  regression_family: string[];
  freeze_boundary: string;
  invalidation_rules: string[];
};

export type ResearchMilestone = {
  name: string;
  deliverable: string;
  pass_condition: string;
};

export type CompetingPaper = {
  canonical_id: string;
  title: string;
  url: string;
  relationship: string;
  difference: string;
  provenance_status?: "version-verified" | "legacy-unversioned";
  source_kind?: "arxiv" | "openreview" | "official-proceedings" | "publisher";
  checked_at?: string;
  source_version?: string;
  source_date?: string;
};

export type Brief = {
  title: string;
  thesis: string;
  motivation: string;
  research_question: string;
  method?: string[];
  evaluation: string[];
  risks: string[];
  first_week: string[];
  paper_ids: string[];
  repo_ids: string[];
  confidence: number;
  status: "provisional" | "researched-draft";
  evidence_note: string;
  non_claims?: string[];
  subquestions?: string[];
  generation_routes?: GenerationRoute[];
  core_design?: CoreDesign;
  what_counts_as_learning_signal?: LearningSignalDefinition;
  validation_funnel?: ValidationStage[];
  human_in_the_loop?: HumanInTheLoop;
  scaling_claim_protocol?: ScalingClaimProtocol;
  experiment?: ExperimentPlan;
  reading_roles?: ReadingRole[];
  route_dictionary_protocol?: RouteDictionaryProtocol;
  milestones?: ResearchMilestone[];
  falsifiers?: string[];
  competitive_landscape?: CompetingPaper[];
  novelty_assessment?: string;
};

export type FeasibilityFactor = {
  id: string;
  score: number;
  max: number;
  rationale: string;
};

export type Feasibility = {
  score: number;
  band: "high" | "medium" | "low";
  screening_estimate?: boolean;
  factors: FeasibilityFactor[];
  assumptions: string[];
  version: string;
};

export type Idea = {
  id: string;
  kind: "research" | "blog";
  origin: "cross-paper" | "cross-paper-reviewed" | "user-specified";
  portfolio_role?: "program" | "work-package";
  parent_idea_id?: string;
  rank_independently?: boolean;
  topic_ids: string[];
  trick_ids: string[];
  repo_ids: string[];
  feasibility: Feasibility;
  brief: Brief;
};

export type Taxon = {
  id: string;
  label: string;
  paper_count: number;
};

export type AtlasMeta = {
  generated_at: string;
  paper_count: number;
  research_entry_count: number;
  context_entry_count: number;
  repo_count: number;
  idea_count: number;
  full_reading_count: number;
  extracted_fulltext_count: number;
  notice: string;
};

export type AtlasCoverage = {
  updated_at: string;
  collection_entries: number;
  canonical_records: number;
  entry_reading_depth: Record<string, number>;
  abstract_entries: number;
  fulltext_extracted: number;
  full_readings: number;
  competitive_landscapes: number;
  canonical_paper_fulltext_extraction_coverage: number;
  canonical_paper_full_reading_coverage: number;
  extraction_failures: Record<string, unknown>[];
  source_access: {
    canonical_records_classified: number;
    paper_records: number;
    non_paper_records: number;
    adapter_supported: number;
    adapter_missing: number;
    by_route: Record<string, number>;
    by_extraction_status: Record<string, number>;
    supported_records_without_readings: number;
  };
  completion_gate: {
    satisfied: boolean;
    rule: string;
  };
};

export type Atlas = {
  meta: AtlasMeta;
  coverage: AtlasCoverage;
  topics: Taxon[];
  tricks: Taxon[];
  papers: Paper[];
  repos: Repo[];
  ideas: Idea[];
  layout?: SemanticLayout;
};

type QualityCohort<Trust extends number, Recall extends number> = {
  node_count: number;
  trustworthiness: number;
  knn_recall: number;
  thresholds: { trustworthiness: Trust; knn_recall: Recall };
};

export type SemanticLayout = {
  schema_version: 3;
  model: "all-minilm";
  embedding: {
    provider: "ollama";
    api: "embed-v1";
    model: "all-minilm";
    artifact_sha256: string;
    dimensions: 384;
    context_length: 256;
    metric: "cosine";
    runtime: "ollama-0.13.1";
    text_schema: "field-budget-v2";
    truncate: false;
    input_sha256: string;
    vector_sha256: string;
  };
  method: "embedding-umap-3d-v1";
  reducer: {
    name: "umap";
    dimensions: 3;
    neighbors: 32;
    min_dist: 0.08;
    metric: "cosine";
    random_seed: 42;
    repulsion_strength: 2;
    negative_sample_rate: 20;
    scale_percentile: 98;
    clip: 1.25;
    extent: 360;
  };
  input_sha256: string;
  node_count: number;
  quality: {
    k: number;
    trustworthiness: number;
    knn_recall: number;
    thresholds: { trustworthiness: 0.9; knn_recall: 0.25 };
    alias_policy: "exclude canonical and identical-text aliases";
    cohort_policy: "research cohorts gated; context reported descriptively";
    cohorts: {
      all: QualityCohort<0.9, 0.25>;
      paper: QualityCohort<0.9, 0.25>;
      context: QualityCohort<0, 0>;
      idea: QualityCohort<0.95, 0.4>;
      taxonomy: QualityCohort<0.88, 0.33>;
    };
  };
  neighbor_count: number;
  neighbors: Record<string, Array<{ id: string; score: number }>>;
  mix_quality: MixQuality;
  cluster_method: "embedding-normalized-kmeans-v1";
  cluster_kind: "coarse embedding neighborhoods";
  cluster_quality: {
    inertia: number;
    mean_inertia: number;
    silhouette: number;
    stability_ari: number;
    fit_count: number;
    silhouette_count: number;
    thresholds: { silhouette: 0; stability_ari: 0.2 };
    min_count: number;
    max_share: number;
  };
  clusters: Array<{
    id: string;
    label: string;
    label_source: "one-to-one taxonomy match";
    label_similarity: number;
    centroid: [number, number, number];
    count: number;
    radius: number;
    medoid: string;
    spread: number;
    terms: string[];
  }>;
  node_clusters: Record<string, string>;
  positions: Record<string, [number, number, number]>;
};

export type DailyScore = {
  score: number;
  reasons: string[];
};

export type DailyRelevance = DailyScore & {
  relevant: boolean;
  lane: "core" | "field" | "math-stat" | "adjacent";
  strong_hits: string[];
  support_hits: string[];
};

export type DailyPaper = {
  id: string;
  url: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  primary_category: string;
  published: string;
  updated: string;
  comment: string;
  relevance: DailyRelevance;
  interest: DailyScore;
  topics: Route[];
  tricks: Route[];
};

export type DailySource = {
  provider: "arXiv";
  query: string;
  timezone: "UTC";
  complete: boolean;
  source_total: number;
  fetched_count: number;
  unique_count: number;
  page_count: number;
};

export type DailyDay = {
  schema_version: 1;
  policy_version: string;
  date: string;
  generated_at: string;
  source: DailySource;
  relevant_count: number;
  shortlist_count: number;
  shortlist_ids: string[];
  papers: DailyPaper[];
};

export type DailySummary = {
  date: string;
  generated_at: string;
  source_total: number;
  fetched_count: number;
  relevant_count: number;
  shortlist_count: number;
  complete: boolean;
  path: string;
};

export type DailyIndex = {
  schema_version: 1;
  generated_at: string;
  days: DailySummary[];
};

export type HostedPaper = DailyPaper & {
  date: string;
  shortlisted: boolean;
  rank: number;
};

export type HostedResult = {
  papers: HostedPaper[];
  total: number;
  limit: number;
  offset: number;
};

export type CorpusMatch = {
  paperId: string;
  rank: number;
};

export type CorpusResult = {
  matches: CorpusMatch[];
  total: number;
  limit: number;
  offset: number;
};

export type GraphNodeKind = "topic" | "trick" | "paper" | "idea";

type GraphNodeBase = {
  id: string;
  label: string;
  count?: number;
  val: number;
  color: string;
  x?: number;
  y?: number;
  z?: number;
  sx?: number;
  sy?: number;
  sz?: number;
  fx?: number;
  fy?: number;
  fz?: number;
  vx?: number;
  vy?: number;
  vz?: number;
};

export type GraphNode =
  | (GraphNodeBase & { kind: "topic"; payload: Taxon })
  | (GraphNodeBase & { kind: "trick"; payload: Taxon })
  | (GraphNodeBase & { kind: "paper"; payload: Paper })
  | (GraphNodeBase & { kind: "idea"; payload: Idea });

export type GraphLink = {
  source: string | GraphNode;
  target: string | GraphNode;
  kind: "topic" | "trick" | "paper" | "idea";
};

export type GraphData = {
  nodes: GraphNode[];
  links: GraphLink[];
};
