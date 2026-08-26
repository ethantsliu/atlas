import type { Atlas, FullReading, Idea, Paper, SemanticLayout } from "../types";

export function makeLayout(): SemanticLayout {
  const ids = [
    "paper-1",
    "paper-2",
    "topic:alignment",
    "topic:world-models",
    "topic:reasoning",
    "topic:representation",
    "trick:variance-control",
    "idea-high",
    "idea-low",
  ];
  const positions = Object.fromEntries(
    ids.map((id, index) => [id, [index, index, index] as [number, number, number]]),
  );
  return {
    schema_version: 3,
    model: "all-minilm",
    embedding: {
      provider: "ollama",
      api: "embed-v1",
      model: "all-minilm",
      artifact_sha256:
        "1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef",
      dimensions: 384,
      context_length: 256,
      metric: "cosine",
      runtime: "ollama-0.13.1",
      text_schema: "field-budget-v2",
      truncate: false,
      input_sha256: "b".repeat(64),
      vector_sha256: "c".repeat(64),
    },
    method: "embedding-umap-3d-v1",
    reducer: {
      name: "umap",
      dimensions: 3,
      neighbors: 24,
      min_dist: 0.12,
      metric: "cosine",
      random_seed: 42,
      repulsion_strength: 2,
      negative_sample_rate: 20,
      scale_percentile: 98,
      clip: 1.25,
      extent: 360,
    },
    input_sha256: "d".repeat(64),
    node_count: ids.length,
    quality: {
      k: 10,
      trustworthiness: 0.95,
      knn_recall: 0.5,
      thresholds: { trustworthiness: 0.9, knn_recall: 0.25 },
      alias_policy: "exclude canonical and identical-text aliases",
      cohort_policy: "research cohorts gated; context reported descriptively",
      cohorts: {
        all: {
          node_count: ids.length,
          trustworthiness: 0.95,
          knn_recall: 0.5,
          thresholds: { trustworthiness: 0.9, knn_recall: 0.25 },
        },
        paper: {
          node_count: 2,
          trustworthiness: 0.95,
          knn_recall: 0.5,
          thresholds: { trustworthiness: 0.9, knn_recall: 0.25 },
        },
        context: {
          node_count: 0,
          trustworthiness: 0.95,
          knn_recall: 0.5,
          thresholds: { trustworthiness: 0, knn_recall: 0 },
        },
        idea: {
          node_count: 2,
          trustworthiness: 0.95,
          knn_recall: 0.5,
          thresholds: { trustworthiness: 0.95, knn_recall: 0.4 },
        },
        taxonomy: {
          node_count: 5,
          trustworthiness: 0.95,
          knn_recall: 0.5,
          thresholds: { trustworthiness: 0.88, knn_recall: 0.33 },
        },
      },
    },
    neighbor_count: 8,
    neighbors: Object.fromEntries(
      ids.map((id, index) => [
        id,
        Array.from({ length: 8 }, (_, offset) => ({
          id: ids[(index + offset + 1) % ids.length],
          score: 0.9 - offset / 10,
        })),
      ]),
    ),
    mix_quality: {
      kind: "cross-kind-layout-v1",
      neighbor_count: 8,
      semantic_routes: {
        topic: { node_count: 4, precision: 0.25, hit_rate: 0.75 },
        trick: { node_count: 1, precision: 0.25, hit_rate: 1 },
        combined: { node_count: 5, precision: 0.25, hit_rate: 0.8 },
      },
      projected_routes: {
        topic: { node_count: 4, precision: 0.25, hit_rate: 0.5 },
        trick: { node_count: 1, precision: 0.25, hit_rate: 1 },
        combined: { node_count: 5, precision: 0.3, hit_rate: 0.6 },
      },
      position_eta_squared: 0.04,
      exact_coordinate_duplicates: 0,
      thresholds: {
        routes: {
          semantic: {
            topic: { precision: 0.2, hit_rate: 0.75 },
            trick: { precision: 0.2, hit_rate: 0.75 },
            combined: { precision: 0.2, hit_rate: 0.75 },
          },
          projected: {
            topic: { precision: 0.2, hit_rate: 0.5 },
            trick: { precision: 0.2, hit_rate: 0.5 },
            combined: { precision: 0.3, hit_rate: 0.5 },
          },
        },
        max_position_eta_squared: 0.05,
        max_exact_coordinate_duplicates: 0,
      },
    },
    cluster_method: "embedding-normalized-kmeans-v1",
    cluster_kind: "coarse embedding neighborhoods",
    cluster_quality: {
      inertia: 1,
      mean_inertia: 0.1,
      silhouette: 0.1,
      stability_ari: 0.5,
      fit_count: 4,
      silhouette_count: 4,
      thresholds: { silhouette: 0, stability_ari: 0.2 },
      min_count: ids.length,
      max_share: 1,
    },
    clusters: [
      {
        id: "cluster-one",
        label: "alignment",
        label_source: "one-to-one taxonomy match",
        label_similarity: 0.8,
        centroid: [3, 3, 3],
        count: ids.length,
        radius: 4,
        medoid: "paper-1",
        spread: 0.4,
        terms: ["alignment"],
      },
    ],
    node_clusters: Object.fromEntries(ids.map((id) => [id, "cluster-one"])),
    positions,
  };
}

const factorDefinitions = [
  ["implementation_leverage", 2.5],
  ["compute_and_data", 2.5],
  ["evaluation_clarity", 2],
  ["novelty_risk", 1.5],
  ["time_to_signal", 1.5],
] as const;

function makeFeasibilityFactors(scores: readonly number[]) {
  return factorDefinitions.map(([id, max], index) => ({
    id,
    score: scores[index],
    max,
    rationale: "Fixture rationale",
  }));
}

export function makePaper(overrides: Partial<Paper> = {}): Paper {
  return {
    id: "paper-1",
    stable_id: "arxiv:0001.00001",
    collection_id: 1,
    record_kind: "paper",
    title: "Alignment Signals",
    url: "https://example.com/paper-1",
    collection_url: "https://example.com/paper-1",
    source: "arxiv",
    authors: ["A. Researcher"],
    published: "2025-01-01",
    categories: ["cs.AI"],
    reading_depth: "abstract",
    topics: [{ id: "alignment", score: 1, evidence: ["alignment"] }],
    tricks: [{ id: "variance-control", score: 1, evidence: ["variance"] }],
    reading: {
      problem: "A problem",
      approach: "An approach",
      evidence: "Some evidence",
      limitations: "A limitation",
      why_it_matters: "Why it matters",
    },
    ...overrides,
  };
}

export function makeFullReading(overrides: Partial<FullReading> = {}): FullReading {
  return {
    stable_id: "arxiv:0001.00001",
    reading_depth: "verified",
    source_provenance: {
      source_locator: "https://arxiv.org/pdf/0001.00001",
      pdf_sha256: "a".repeat(64),
      text_sha256: "b".repeat(64),
      page_count: 12,
      extracted_at: "2026-08-23T12:00:00+00:00",
      review_pass: "secondary-verified-v1",
    },
    question: "Does the intervention improve a sealed outcome?",
    key_findings: [
      {
        claim: "The intervention improves the registered outcome.",
        evidence: "The held-out comparison reports a positive effect.",
        attribution: "author-reported",
        anchors: [{ page: 4, section: "3.2 Results" }],
      },
    ],
    method: {
      core_idea: "Compare an intervention with a matched control.",
      mechanism: "The intervention changes the learning signal.",
      assumptions: ["The evaluator is independent of the intervention."],
    },
    techniques: [{ id: "variance-control", role: "Matches stochastic variation." }],
    evaluations: [
      {
        setting: "Held-out tasks",
        metric: "Success rate",
        result: "A positive registered effect",
        baseline: "Matched control",
      },
    ],
    limitations: ["The evaluation uses one model family."],
    failure_modes: ["The effect may reverse under a stronger optimizer."],
    reusable_insights: ["Seal the outcome before tuning the intervention."],
    open_questions: ["Does the effect transfer to another model family?"],
    competitive_landscape: Array.from({ length: 3 }, (_, index) => ({
      canonical_id: `arxiv:prior-${index + 1}`,
      title: `Primary competitor ${index + 1}`,
      url: `https://arxiv.org/abs/prior-${index + 1}`,
      relationship: "direct baseline",
      difference: "The competitor does not use the registered intervention.",
      source_kind: "arxiv" as const,
      checked_at: "2026-08-23",
      source_version: `v${index + 1}`,
    })),
    novelty_assessment: {
      author_claim: "The intervention is new.",
      evidence: "The paper compares against the closest cited baseline.",
      reviewer_inference: "The defensible novelty is the registered comparison.",
    },
    verification: {
      reviewer_id: "reviewer-2",
      checked_at: "2026-08-23",
      passage_check: "All cited passages were checked against the pinned PDF.",
      competitor_check: "All competitor records and versions were checked.",
    },
    confidence: 0.9,
    reviewer_notes: "Keep the causal claim narrower than the author framing.",
    ...overrides,
  };
}

export function makeIdea(overrides: Partial<Idea> = {}): Idea {
  return {
    id: "idea-high",
    kind: "research",
    origin: "cross-paper",
    topic_ids: ["alignment"],
    trick_ids: ["variance-control"],
    repo_ids: [],
    feasibility: {
      score: 6.5,
      band: "medium",
      screening_estimate: true,
      factors: makeFeasibilityFactors([2, 2, 0.9, 0.3, 1.3]),
      assumptions: [],
      version: "1",
    },
    brief: {
      title: "Test alignment signals",
      thesis: "A thesis",
      motivation: "A motivation",
      research_question: "A question?",
      method: ["Run a test"],
      evaluation: ["Measure an outcome"],
      risks: ["A risk"],
      first_week: ["Build a fixture"],
      paper_ids: ["arxiv:0001.00001"],
      repo_ids: [],
      confidence: 0.8,
      status: "provisional",
      evidence_note: "A note",
    },
    ...overrides,
  };
}

export function makeAtlas(overrides: Partial<Atlas> = {}): Atlas {
  const firstPaper = makePaper();
  const secondPaper = makePaper({
    id: "paper-2",
    stable_id: "arxiv:0002.00002",
    collection_id: 2,
    title: "World Model Search",
    reading_depth: "metadata",
    topics: [{ id: "world-models", score: 1, evidence: ["world model"] }],
    tricks: [],
  });

  return {
    meta: {
      generated_at: "2026-01-01",
      paper_count: 2,
      research_entry_count: 2,
      context_entry_count: 0,
      repo_count: 0,
      idea_count: 2,
      full_reading_count: 0,
      extracted_fulltext_count: 0,
      notice: "Test fixture",
    },
    coverage: {
      updated_at: "2026-01-01",
      collection_entries: 2,
      canonical_records: 2,
      entry_reading_depth: { abstract: 1, metadata: 1 },
      abstract_entries: 1,
      fulltext_extracted: 0,
      full_readings: 0,
      competitive_landscapes: 0,
      canonical_paper_fulltext_extraction_coverage: 0,
      canonical_paper_full_reading_coverage: 0,
      extraction_failures: [],
      source_access: {
        canonical_records_classified: 2,
        paper_records: 2,
        non_paper_records: 0,
        adapter_supported: 0,
        adapter_missing: 2,
        by_route: { manual_review: 2 },
        by_extraction_status: { adapter_missing: 2 },
        supported_records_without_readings: 0,
      },
      completion_gate: { satisfied: false, rule: "Test completion rule" },
    },
    topics: [
      { id: "alignment", label: "Alignment", paper_count: 1 },
      { id: "world-models", label: "World Models", paper_count: 1 },
      { id: "reasoning", label: "Reasoning", paper_count: 0 },
      { id: "representation", label: "Representation", paper_count: 0 },
    ],
    tricks: [{ id: "variance-control", label: "Variance Control", paper_count: 1 }],
    papers: [firstPaper, secondPaper],
    repos: [],
    ideas: [
      makeIdea(),
      makeIdea({
        id: "idea-low",
        topic_ids: ["world-models"],
        trick_ids: [],
        repo_ids: [],
        feasibility: {
          score: 4,
          band: "low",
          screening_estimate: true,
          factors: makeFeasibilityFactors([1, 1, 0.8, 0.3, 0.9]),
          assumptions: [],
          version: "1",
        },
        brief: {
          ...makeIdea().brief,
          title: "Explore world models",
          paper_ids: ["paper-2"],
          repo_ids: [],
        },
      }),
    ],
    ...overrides,
  };
}
