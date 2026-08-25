import { describe, expect, it } from "vitest";
import {
  atlasValidationError,
  readingError,
  isAtlasPayload,
  isReadingPayload,
} from "./atlas";
import { makeAtlas, makeFullReading } from "../test/fixtures";
import type { Atlas, CompetingPaper, FullReading } from "../types";

const READING_PATH = "/data/readings/arxiv-0001-00001--0123456789ab-fedcba987654.json";

function atlasWithReading(depth: FullReading["reading_depth"] = "verified"): Atlas {
  const atlas = makeAtlas();
  atlas.papers[0].reading_depth = depth;
  atlas.papers[0].full_reading_path = READING_PATH;
  atlas.meta.full_reading_count = 1;
  atlas.coverage.full_readings = 1;
  return atlas;
}

describe("isAtlasPayload", () => {
  it("accepts the atlas contract and rejects malformed payloads", () => {
    expect(isAtlasPayload(makeAtlas())).toBe(true);
    expect(isAtlasPayload({ meta: {}, papers: [] })).toBe(false);
    expect(isAtlasPayload(null)).toBe(false);
  });

  it("rejects a payload with a malformed nested paper", () => {
    const atlas = makeAtlas();
    atlas.papers[0].reading = { ...atlas.papers[0].reading, problem: 42 as never };
    expect(isAtlasPayload(atlas)).toBe(false);
  });

  it("rejects bibliographic values that would crash timeline rendering", () => {
    const atlas = makeAtlas();
    atlas.papers[0].published = 2026 as never;

    expect(atlasValidationError(atlas)).toBe(
      "invalid paper at index 0: invalid optional bibliographic fields",
    );
  });

  it("rejects unsafe bibliographic URLs", () => {
    const paperUrl = makeAtlas();
    paperUrl.papers[0].url = "javascript:alert(1)";
    expect(atlasValidationError(paperUrl)).toBe(
      "invalid paper at index 0: invalid bibliographic fields",
    );

    const collectionUrl = makeAtlas();
    collectionUrl.papers[0].collection_url = "http://example.com/paper";
    expect(atlasValidationError(collectionUrl)).toBe(
      "invalid paper at index 0: invalid bibliographic fields",
    );
  });

  it("requires a safe lazy detail path exactly at substantive depth", () => {
    expect(atlasValidationError(atlasWithReading())).toBeNull();

    const missingPath = atlasWithReading();
    delete missingPath.papers[0].full_reading_path;
    expect(atlasValidationError(missingPath)).toBe(
      "invalid paper at index 0: reading depth and detail path disagree",
    );

    const unsafePath = atlasWithReading();
    unsafePath.papers[0].full_reading_path = "/data/readings/../secret.json";
    expect(atlasValidationError(unsafePath)).toBe(
      "invalid paper at index 0: invalid full reading path",
    );

    const legacyBody = atlasWithReading() as Atlas & {
      papers: Array<Atlas["papers"][number] & { full_reading?: unknown }>;
    };
    legacyBody.papers[0].full_reading = makeFullReading();
    expect(atlasValidationError(legacyBody)).toBe(
      "invalid paper at index 0: legacy embedded reading is not allowed",
    );
  });

  it("rejects a payload with a malformed feasibility contract", () => {
    const atlas = makeAtlas();
    atlas.ideas[0].feasibility.score = Number.NaN;
    expect(isAtlasPayload(atlas)).toBe(false);
  });

  it("rejects feasibility totals, bands, and factor maxima that drift", () => {
    const invalidTotal = makeAtlas();
    invalidTotal.ideas[0].feasibility.factors[0].score = 0;
    expect(atlasValidationError(invalidTotal)).toBe("invalid idea at index 0");

    const invalidBand = makeAtlas();
    invalidBand.ideas[0].feasibility.band = "low";
    expect(atlasValidationError(invalidBand)).toBe("invalid idea at index 0");

    const invalidMaximum = makeAtlas();
    invalidMaximum.ideas[0].feasibility.factors[0].max = 3;
    expect(atlasValidationError(invalidMaximum)).toBe("invalid idea at index 0");

    const factorAboveMaximum = makeAtlas();
    factorAboveMaximum.ideas[0].feasibility.factors[0].score = 2.6;
    expect(atlasValidationError(factorAboveMaximum)).toBe("invalid idea at index 0");

    const unknownFeasibility = makeAtlas();
    Object.assign(unknownFeasibility.ideas[0].feasibility, { hidden_score: 1 });
    expect(atlasValidationError(unknownFeasibility)).toBe("invalid idea at index 0");

    const unknownFactor = makeAtlas();
    Object.assign(unknownFactor.ideas[0].feasibility.factors[0], { hidden: true });
    expect(atlasValidationError(unknownFactor)).toBe("invalid idea at index 0");

    const blankVersion = makeAtlas();
    blankVersion.ideas[0].feasibility.version = " ";
    expect(atlasValidationError(blankVersion)).toBe("invalid idea at index 0");

    const blankAssumption = makeAtlas();
    blankAssumption.ideas[0].feasibility.assumptions = [" "];
    expect(atlasValidationError(blankAssumption)).toBe("invalid idea at index 0");
  });

  it("rejects malformed idea fields that are rendered directly", () => {
    const invalidKind = makeAtlas();
    invalidKind.ideas[0].kind = { label: "research" } as never;
    expect(isAtlasPayload(invalidKind)).toBe(false);

    const invalidOrigin = makeAtlas();
    invalidOrigin.ideas[0].origin = { label: "private-source" } as never;
    expect(isAtlasPayload(invalidOrigin)).toBe(false);

    const invalidNovelty = makeAtlas();
    invalidNovelty.ideas[0].brief.novelty_assessment = ["unsafe"] as never;
    expect(isAtlasPayload(invalidNovelty)).toBe(false);

    const invalidConfidence = makeAtlas();
    invalidConfidence.ideas[0].brief.confidence = "high" as never;
    expect(isAtlasPayload(invalidConfidence)).toBe(false);

    const invalidList = makeAtlas();
    invalidList.ideas[0].brief.evaluation = [1] as never;
    expect(isAtlasPayload(invalidList)).toBe(false);

    for (const field of ["motivation", "evidence_note"] as const) {
      const missingText = makeAtlas();
      delete (
        missingText.ideas[0].brief as Partial<(typeof missingText.ideas)[0]["brief"]>
      )[field];
      expect(isAtlasPayload(missingText)).toBe(false);
    }
  });

  it("rejects unknown brief fields before they can disappear from the UI", () => {
    const atlas = makeAtlas();
    const brief = atlas.ideas[0].brief as (typeof atlas.ideas)[0]["brief"] & {
      unrendered_protocol?: string;
    };
    brief.unrendered_protocol = "This must not pass silently.";

    expect(isAtlasPayload(atlas)).toBe(false);
  });

  it("validates specialized brief protocols instead of dropping them", () => {
    const atlas = makeAtlas();
    const brief = atlas.ideas[0].brief;
    brief.reading_roles = [
      {
        paper_id: brief.paper_ids[0],
        role: "substantive support",
        use: "Defines the registered comparison.",
      },
    ];
    brief.route_dictionary_protocol = {
      shared_axes: ["lookup versus inference"],
      markov_family: ["unigram"],
      regression_family: ["ridge"],
      freeze_boundary: "Hash every route before confirmation.",
      invalidation_rules: ["Abstain when routes are collinear."],
    };
    brief.milestones = [
      {
        name: "Basis audit",
        deliverable: "Pinned route registry",
        pass_condition: "Every positive and abstention control passes.",
      },
    ];
    brief.validation_funnel = [
      { stage: "Basis", cost: "low", gate: "Recover planted routes." },
    ];
    brief.generation_routes = [
      {
        route: "mutation",
        mechanism: "Mutate a typed environment genome.",
        examples: "Grid layouts",
        best_when: "Simulation is cheap.",
      },
    ];
    brief.core_design = {
      unit_of_search: "Immutable environment",
      generator: "Typed mutation operators",
      fitness: ["Sealed transfer uplift"],
      selection: "Successive halving",
      critical_control: "Equal-compute replacement",
    };
    brief.what_counts_as_learning_signal = {
      answer: "A causal training effect on a sealed outcome.",
      evidence_hierarchy: [
        {
          level: 1,
          name: "Operational",
          evidence: "Property tests pass.",
          does_not_show: "That training learns.",
        },
      ],
      recommended_statistics: ["Marginal transfer uplift"],
    };
    brief.human_in_the_loop = {
      answer: "Humans adjudicate ambiguous safety cases.",
      humans_not_needed_for: ["Deterministic property tests"],
      humans_needed_for: ["Ambiguous semantic validity"],
      measurement: "Reviewer agreement and escalation rate",
    };
    brief.scaling_claim_protocol = {
      answer: "A small run is a proxy, not a scaling claim.",
      prospective_design: ["Freeze a predictor before the target tier."],
      supporting_evidence: ["Target-tier calibration"],
      claim_blockers: ["Rank reversal"],
      claim_language: "Evidence within the tested range only.",
    };
    expect(atlasValidationError(atlas)).toBeNull();

    brief.reading_roles.push({ ...brief.reading_roles[0] });
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    brief.reading_roles.pop();

    brief.route_dictionary_protocol.shared_axes = [] as string[];
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    brief.route_dictionary_protocol = {
      ...brief.route_dictionary_protocol,
      freeze_boundary: 42 as never,
    };
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.route_dictionary_protocol = undefined;
    brief.milestones = [{ name: "Missing detail" } as never];
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.milestones = undefined;
    brief.validation_funnel = ["untyped gate" as never];
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.validation_funnel = undefined;
    brief.generation_routes = [];
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.generation_routes = undefined;
    brief.core_design = { ...brief.core_design!, fitness: [] };
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.core_design = undefined;
    brief.what_counts_as_learning_signal = {
      ...brief.what_counts_as_learning_signal!,
      evidence_hierarchy: [],
    };
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.what_counts_as_learning_signal = undefined;
    brief.human_in_the_loop = {
      ...brief.human_in_the_loop!,
      humans_needed_for: [],
    };
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    brief.human_in_the_loop = undefined;
    brief.scaling_claim_protocol = {
      ...brief.scaling_claim_protocol!,
      claim_blockers: [""],
    };
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
  });

  it("enforces provisional evidence caps", () => {
    const atlas = makeAtlas();
    expect(atlasValidationError(atlas)).toBeNull();

    atlas.ideas[0].feasibility.screening_estimate = undefined;
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    atlas.ideas[0].feasibility.screening_estimate = true;
    atlas.ideas[0].feasibility.factors[2].score = 1;
    atlas.ideas[0].feasibility.score = 6.6;
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
  });

  it("requires a rendered primary outcome for researched experiments", () => {
    const atlas = makeAtlas();
    atlas.ideas[0].origin = "user-specified";
    atlas.ideas[0].brief.status = "researched-draft";
    atlas.ideas[0].brief.novelty_assessment = "A sealed outcome is the narrow delta.";
    const competitors = Array.from({ length: 10 }, (_, index) => ({
      canonical_id: `arxiv:prior-${index}`,
      title: `Primary prior ${index}`,
      url: `https://arxiv.org/abs/prior-${index}v1`,
      relationship: "direct competitor",
      difference: "It lacks the sealed target outcome.",
      provenance_status: "version-verified" as const,
      source_kind: "arxiv" as const,
      source_version: `arXiv:prior-${index}v1`,
      source_date: "2026-08-01",
      checked_at: "2026-08-23",
    }));
    atlas.ideas[0].brief.competitive_landscape = competitors;
    atlas.ideas[0].feasibility.screening_estimate = false;
    atlas.ideas[0].brief.experiment = {
      primary_hypothesis: "The intervention works.",
      secondary_hypothesis: "The effect transfers.",
      domains: ["Held-out task"],
      baselines: ["Matched control"],
      ablations: ["Remove route"],
      decision_rule: "Reject if the gate fails.",
    };
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    atlas.ideas[0].brief.experiment.primary_outcome = "Sealed forecast score";
    expect(atlasValidationError(atlas)).toBeNull();

    const originalMethod = atlas.ideas[0].brief.method;
    atlas.ideas[0].brief.method = [" "];
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    atlas.ideas[0].brief.method = originalMethod;

    for (const field of ["evaluation", "risks", "first_week"] as const) {
      const original = atlas.ideas[0].brief[field];
      atlas.ideas[0].brief[field] = [" "];
      expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
      atlas.ideas[0].brief[field] = original;
    }

    atlas.ideas[0].brief.method = [];
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    atlas.ideas[0].brief.method = ["Run a test"];

    atlas.ideas[0].brief.competitive_landscape.length = 4;
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    atlas.ideas[0].brief.competitive_landscape = competitors;

    const experiment = atlas.ideas[0].brief
      .experiment as (typeof atlas.ideas)[0]["brief"]["experiment"] &
      Record<string, unknown>;
    experiment.unrendered_result = "must not disappear";
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
  });

  it("requires explicit and internally consistent brief competitor provenance", () => {
    const atlas = makeAtlas();
    atlas.ideas[0].brief.competitive_landscape = [
      {
        canonical_id: "arxiv:1",
        title: "Primary prior",
        url: "https://arxiv.org/abs/1v2",
        relationship: "closest prior",
        difference: "The proposal adds a sealed test.",
        provenance_status: "version-verified",
        source_kind: "arxiv",
        source_version: "arXiv:1v2",
        source_date: "2026-08-01",
        checked_at: "2026-08-23",
      },
    ];
    expect(atlasValidationError(atlas)).toBeNull();

    const competitor = atlas.ideas[0].brief.competitive_landscape[0] as CompetingPaper &
      Record<string, unknown>;
    competitor.hidden_claim = "must not bypass the contract";
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    delete competitor.hidden_claim;

    atlas.ideas[0].brief.competitive_landscape[0].url =
      "https://ojs.aaai.org/index.php/AAAI/article/view/34008";
    expect(atlasValidationError(atlas)).toBeNull();
    atlas.ideas[0].brief.competitive_landscape[0].url = "https://arxiv.org/abs/1v2";

    atlas.ideas[0].brief.competitive_landscape[0].source_date = 20260801 as never;
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    atlas.ideas[0].brief.competitive_landscape[0].source_date = "2026-08-01";
    atlas.ideas[0].brief.competitive_landscape.push({
      ...atlas.ideas[0].brief.competitive_landscape[0],
    });
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    atlas.ideas[0].brief.competitive_landscape.pop();
    atlas.ideas[0].brief.competitive_landscape[0].url = "https://example.com/paper";
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");

    atlas.ideas[0].brief.competitive_landscape[0].url = "https://arxiv.org/abs/1v2";
    atlas.ideas[0].brief.competitive_landscape[0].provenance_status =
      "legacy-unversioned";
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
    delete atlas.ideas[0].brief.competitive_landscape[0].source_version;
    delete atlas.ideas[0].brief.competitive_landscape[0].source_date;
    expect(atlasValidationError(atlas)).toBeNull();

    delete atlas.ideas[0].brief.competitive_landscape[0].provenance_status;
    expect(atlasValidationError(atlas)).toBe("invalid idea at index 0");
  });

  it("rejects unknown lifecycle labels instead of rendering them as valid", () => {
    const invalidOrigin = makeAtlas();
    invalidOrigin.ideas[0].origin = "mystery-source" as never;
    expect(isAtlasPayload(invalidOrigin)).toBe(false);

    const invalidStatus = makeAtlas();
    invalidStatus.ideas[0].brief.status = "finished" as never;
    expect(isAtlasPayload(invalidStatus)).toBe(false);

    const invalidReadingDepth = makeAtlas();
    invalidReadingDepth.papers[0].reading_depth = "skimmed" as never;
    expect(isAtlasPayload(invalidReadingDepth)).toBe(false);
  });

  it("rejects idea scores outside their declared scale", () => {
    const invalidScore = makeAtlas();
    invalidScore.ideas[0].feasibility.score = 10.1;
    expect(isAtlasPayload(invalidScore)).toBe(false);
  });

  it("rejects legacy personal source data", () => {
    const atlas = makeAtlas();
    Object.assign(atlas, { personal_sources: { legacy: true } });
    expect(atlasValidationError(atlas)).toBe("personal source data is not allowed");
  });

  it("rejects context entries presented as paper readings", () => {
    const atlas = makeAtlas();
    atlas.papers[0].record_kind = "non_paper_context";
    atlas.meta.research_entry_count = 1;
    atlas.meta.context_entry_count = 1;
    expect(atlasValidationError(atlas)).toBe(
      "invalid paper at index 0: context record presented as a paper reading",
    );
  });

  it("rejects inconsistent entry-level counts", () => {
    const atlas = makeAtlas();
    atlas.meta.research_entry_count = 1;
    expect(atlasValidationError(atlas)).toBe("inconsistent atlas counts");
  });

  it("requires authoritative metadata and coverage fields", () => {
    const missingCoverage = makeAtlas() as unknown as { coverage?: unknown };
    delete missingCoverage.coverage;
    expect(isAtlasPayload(missingCoverage)).toBe(false);

    const missingGeneratedAt = makeAtlas() as unknown as {
      meta: { generated_at?: string };
    };
    delete missingGeneratedAt.meta.generated_at;
    expect(isAtlasPayload(missingGeneratedAt)).toBe(false);

    const missingCoverageTimestamp = makeAtlas() as unknown as {
      coverage: { updated_at?: string };
    };
    delete missingCoverageTimestamp.coverage.updated_at;
    expect(isAtlasPayload(missingCoverageTimestamp)).toBe(false);
  });

  it("rejects idea evidence IDs that are absent from the collection", () => {
    const atlas = makeAtlas();
    atlas.ideas[0].brief.paper_ids = ["arxiv:missing"];
    expect(atlasValidationError(atlas)).toBe(
      "unresolved idea paper reference at index 0",
    );
  });

  it("rejects unknown taxonomy references", () => {
    const unknownPaperTopic = makeAtlas();
    unknownPaperTopic.papers[0].topics[0].id = "missing-topic";
    expect(atlasValidationError(unknownPaperTopic)).toBe(
      "unknown paper topic reference at index 0",
    );

    const unknownPaperTrick = makeAtlas();
    unknownPaperTrick.papers[0].tricks[0].id = "missing-technique";
    expect(atlasValidationError(unknownPaperTrick)).toBe(
      "unknown paper technique reference at index 0",
    );

    const unknownIdeaTopic = makeAtlas();
    unknownIdeaTopic.ideas[0].topic_ids = ["missing-topic"];
    expect(atlasValidationError(unknownIdeaTopic)).toBe(
      "unknown idea topic reference at index 0",
    );

    const unknownIdeaTrick = makeAtlas();
    unknownIdeaTrick.ideas[0].trick_ids = ["missing-technique"];
    expect(atlasValidationError(unknownIdeaTrick)).toBe(
      "unknown idea technique reference at index 0",
    );
  });

  it("rejects all repository data", () => {
    const inventory = makeAtlas();
    inventory.repos.push({ id: "repo:private" } as never);
    inventory.meta.repo_count = 1;
    expect(atlasValidationError(inventory)).toBe("repository data is not allowed");

    const idea = makeAtlas();
    idea.ideas[0].repo_ids = ["repo:private"];
    expect(atlasValidationError(idea)).toBe("repository data is not allowed");

    const brief = makeAtlas();
    brief.ideas[0].brief.repo_ids = ["repo:private"];
    expect(atlasValidationError(brief)).toBe("repository data is not allowed");
  });

  it("rejects duplicate and colliding graph node IDs", () => {
    const duplicatePaper = makeAtlas();
    duplicatePaper.papers[1].id = duplicatePaper.papers[0].id;
    expect(atlasValidationError(duplicatePaper)).toBe("duplicate graph node IDs");

    const crossKindCollision = makeAtlas();
    crossKindCollision.ideas[0].id = crossKindCollision.papers[0].id;
    expect(atlasValidationError(crossKindCollision)).toBe("duplicate graph node IDs");
  });

  it("rejects duplicate idea IDs before graph construction", () => {
    const atlas = makeAtlas();
    atlas.ideas.push({ ...atlas.ideas[0] });
    atlas.meta.idea_count += 1;
    expect(atlasValidationError(atlas)).toBe("duplicate idea IDs");
  });

  it("requires work packages to resolve to explicitly ranked programs", () => {
    const valid = makeAtlas();
    valid.ideas[0].portfolio_role = "program";
    valid.ideas[0].rank_independently = true;
    valid.ideas[1].portfolio_role = "work-package";
    valid.ideas[1].parent_idea_id = valid.ideas[0].id;
    valid.ideas[1].rank_independently = false;
    expect(atlasValidationError(valid)).toBeNull();

    const missingParent = makeAtlas();
    missingParent.ideas[0].portfolio_role = "work-package";
    missingParent.ideas[0].parent_idea_id = "missing-program";
    missingParent.ideas[0].rank_independently = false;
    expect(atlasValidationError(missingParent)).toBe(
      "unresolved work-package parent at idea index 0",
    );

    const independentlyRankedPackage = makeAtlas();
    independentlyRankedPackage.ideas[0].portfolio_role = "program";
    independentlyRankedPackage.ideas[0].rank_independently = true;
    independentlyRankedPackage.ideas[1].portfolio_role = "work-package";
    independentlyRankedPackage.ideas[1].parent_idea_id =
      independentlyRankedPackage.ideas[0].id;
    independentlyRankedPackage.ideas[1].rank_independently = true;
    expect(atlasValidationError(independentlyRankedPackage)).toBe(
      "invalid work-package metadata at idea index 1",
    );
  });
});

describe("full reading detail validation", () => {
  it("accepts a complete detail payload bound to its index record", () => {
    const reading = makeFullReading();
    expect(
      isReadingPayload(reading, {
        stableId: reading.stable_id,
        readingDepth: reading.reading_depth,
      }),
    ).toBe(true);
  });

  it("accepts exactly one HTML source identity", () => {
    const reading = makeFullReading();
    const provenance = { ...reading.source_provenance } as Record<string, unknown>;
    delete provenance.pdf_sha256;
    provenance.source_format = "html";
    provenance.source_sha256 = "c".repeat(64);
    const htmlReading = { ...reading, source_provenance: provenance };

    expect(
      isReadingPayload(htmlReading, {
        stableId: reading.stable_id,
        readingDepth: reading.reading_depth,
      }),
    ).toBe(true);
    expect(
      isReadingPayload({
        ...htmlReading,
        source_provenance: { ...provenance, pdf_sha256: "a".repeat(64) },
      }),
    ).toBe(false);
    expect(
      isReadingPayload({
        ...htmlReading,
        source_provenance: { ...provenance, source_sha256: undefined },
      }),
    ).toBe(false);
  });

  it("rejects missing anchors, competitors, and source revision pins", () => {
    const reading = makeFullReading();
    expect(
      isReadingPayload({
        ...reading,
        key_findings: [{ ...reading.key_findings[0], anchors: [] }],
      }),
    ).toBe(false);
    expect(isReadingPayload({ ...reading, competitive_landscape: [] })).toBe(false);
    expect(
      isReadingPayload({
        ...reading,
        source_provenance: {
          ...reading.source_provenance,
          pdf_sha256: "not-a-hash",
        },
      }),
    ).toBe(false);
  });

  it("matches the authoritative reading schema on semantic and exact-key failures", () => {
    const reading = makeFullReading();
    expect(isReadingPayload({ ...reading, question: "" })).toBe(false);
    expect(
      isReadingPayload({
        ...reading,
        key_findings: [
          {
            ...reading.key_findings[0],
            anchors: [
              {
                ...reading.key_findings[0].anchors[0],
                page: reading.source_provenance.page_count + 1,
              },
            ],
          },
        ],
      }),
    ).toBe(false);

    const unknownField = { ...reading } as FullReading & { hidden_claim?: string };
    unknownField.hidden_claim = "This must not bypass the schema.";
    expect(isReadingPayload(unknownField)).toBe(false);

    const duplicateCompetitors = reading.competitive_landscape.map(
      (competitor, index) =>
        index === 1
          ? {
              ...competitor,
              canonical_id: reading.competitive_landscape[0].canonical_id,
            }
          : competitor,
    );
    expect(
      isReadingPayload({
        ...reading,
        competitive_landscape: duplicateCompetitors,
      }),
    ).toBe(false);

    const nonPrimaryCompetitors = reading.competitive_landscape.map(
      (competitor, index) =>
        index === 0 ? { ...competitor, url: "https://example.com/paper" } : competitor,
    );
    expect(
      isReadingPayload({
        ...reading,
        competitive_landscape: nonPrimaryCompetitors,
      }),
    ).toBe(false);

    const officialNeuripsCompetitors = reading.competitive_landscape.map(
      (competitor, index) =>
        index === 0
          ? {
              ...competitor,
              url: "https://proceedings.neurips.cc/paper_files/paper/2024/hash/example-Abstract-Conference.html",
            }
          : competitor,
    );
    expect(
      isReadingPayload({
        ...reading,
        competitive_landscape: officialNeuripsCompetitors,
      }),
    ).toBe(true);

    for (const url of [
      "https://papers.nips.cc/paper_files/paper/2024/hash/example.html",
      "https://www.jmlr.org/papers/v26/24-0065.html",
      "https://openaccess.thecvf.com/content_CVPR_2019/html/example.html",
    ]) {
      expect(
        isReadingPayload({
          ...reading,
          competitive_landscape: reading.competitive_landscape.map(
            (competitor, index) => (index === 0 ? { ...competitor, url } : competitor),
          ),
        }),
      ).toBe(true);
    }
  });

  it("requires second-review lineage at verified depth", () => {
    const reading = makeFullReading();
    expect(isReadingPayload({ ...reading, verification: undefined })).toBe(false);
  });

  it("rejects detail identity and depth drift from the compact index", () => {
    const reading = makeFullReading();
    expect(
      readingError(reading, {
        stableId: "arxiv:different-paper",
        readingDepth: "verified",
      }),
    ).toBe("full reading ID mismatch");
    expect(
      readingError(reading, {
        stableId: reading.stable_id,
        readingDepth: "full_text",
      }),
    ).toBe("full reading depth mismatch");
  });

  it("rejects unsafe reading source URLs", () => {
    const reading = makeFullReading();
    reading.source_provenance.source_locator = "file:///tmp/private.pdf";

    expect(readingError(reading)).toBe("invalid full reading contract");
  });
});
