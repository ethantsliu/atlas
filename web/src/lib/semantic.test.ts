import { describe, expect, it } from "vitest";
import { makeAtlas, makeLayout } from "../test/fixtures";
import type { SemanticLayout } from "../types";
import { atlasValidationError } from "./atlas";
import { atlasScope, isLayout, layoutError } from "./semantic";

function rejects(change: (layout: SemanticLayout) => void): void {
  const atlas = makeAtlas({ layout: makeLayout() });
  change(atlas.layout as SemanticLayout);
  expect(layoutError(atlas.layout, atlasScope(atlas))).not.toBeNull();
  expect(atlasValidationError(atlas)).not.toBeNull();
}

describe("semantic layout guard", () => {
  it("accepts the central fixture through both runtime boundaries", () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const scope = atlasScope(atlas);

    expect(layoutError(atlas.layout, scope)).toBeNull();
    expect(isLayout(atlas.layout, scope)).toBe(true);
    expect(atlasValidationError(atlas)).toBeNull();
  });

  it("pins schema, model, reducer, and complete embedding provenance", () => {
    const changes: Array<(layout: SemanticLayout) => void> = [
      (layout) => {
        layout.schema_version = 2 as never;
      },
      (layout) => {
        layout.embedding.artifact_sha256 = "0".repeat(64);
      },
      (layout) => {
        layout.embedding.context_length = 512 as never;
      },
      (layout) => {
        layout.embedding.runtime = "ollama-latest" as never;
      },
      (layout) => {
        layout.embedding.text_schema = "legacy" as never;
      },
      (layout) => {
        layout.embedding.truncate = true as never;
      },
      (layout) => {
        layout.reducer.neighbors = 15 as never;
      },
      (layout) => {
        layout.input_sha256 = "not-a-hash";
      },
      (layout) => {
        (layout.embedding as unknown as Record<string, unknown>).extra = true;
      },
    ];

    changes.forEach(rejects);
  });

  it("accepts and binds an optional orientation receipt", () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const layout = atlas.layout as SemanticLayout;
    layout.orientation = {
      method: "orthogonal-procrustes-3d-v1",
      anchor_count: layout.node_count,
      reference_sha256: "e".repeat(64),
      determinant: -1,
      rmsd_before: 4,
      rmsd_after: 1,
    };

    expect(layoutError(layout, atlasScope(atlas))).toBeNull();
    rejects((candidate) => {
      candidate.orientation = { ...layout.orientation!, anchor_count: 3 };
    });
    rejects((candidate) => {
      candidate.orientation = { ...layout.orientation!, determinant: 0.99 };
    });
    rejects((candidate) => {
      candidate.orientation = { ...layout.orientation!, rmsd_after: 5 };
    });
    rejects((candidate) => {
      candidate.orientation = { ...layout.orientation!, reference_sha256: "bad" };
    });
    rejects((candidate) => {
      candidate.orientation = {
        ...layout.orientation!,
        extra: true,
      } as never;
    });
  });

  it("requires quality aliases, cohorts, and literal thresholds", () => {
    rejects((layout) => {
      layout.quality.k = 9;
    });
    rejects((layout) => {
      layout.quality.alias_policy = "include aliases" as never;
    });
    rejects((layout) => {
      layout.quality.cohort_policy = "all cohorts gated" as never;
    });
    rejects((layout) => {
      delete (layout.quality as Partial<SemanticLayout["quality"]>).cohort_policy;
    });
    rejects((layout) => {
      layout.quality.thresholds.knn_recall = 0.2 as never;
    });
    rejects((layout) => {
      layout.quality.cohorts.paper.node_count += 1;
    });
    rejects((layout) => {
      layout.quality.cohorts.all.trustworthiness = 0.91;
    });
    rejects((layout) => {
      delete (
        layout.quality.cohorts.paper as Partial<
          SemanticLayout["quality"]["cohorts"]["paper"]
        >
      ).thresholds;
    });
    rejects((layout) => {
      layout.quality.cohorts.context = {
        node_count: 0,
        trustworthiness: 1,
        knn_recall: 1,
        thresholds: { trustworthiness: 0, knn_recall: 0 },
      };
    });
    rejects((layout) => {
      layout.quality.cohorts.idea.thresholds.trustworthiness = 0.9 as never;
    });
    rejects((layout) => {
      layout.quality.cohorts.taxonomy.knn_recall = 0.32;
    });
  });

  it("requires fixed cross-kind retrieval and positional mixing gates", () => {
    rejects((layout) => {
      layout.mix_quality.semantic_routes.trick.hit_rate = 0.74;
    });
    rejects((layout) => {
      layout.mix_quality.projected_routes.combined.precision = 0.29;
    });
    rejects((layout) => {
      layout.mix_quality.position_eta_squared = 0.051;
    });
    rejects((layout) => {
      layout.mix_quality.exact_coordinate_duplicates = 1;
    });
    rejects((layout) => {
      layout.mix_quality.thresholds.routes.projected.topic.hit_rate = 0.4 as never;
    });
  });

  it("requires exact, ordered, unique, and graph-bound neighbors", () => {
    rejects((layout) => {
      layout.neighbor_count = 7;
    });
    rejects((layout) => {
      delete layout.neighbors["paper-1"];
    });
    rejects((layout) => {
      layout.neighbors["paper-1"][1].score = 0.95;
    });
    rejects((layout) => {
      layout.neighbors["paper-1"][1].id = layout.neighbors["paper-1"][0].id;
    });
    rejects((layout) => {
      layout.neighbors["paper-1"][0].id = "missing-node";
    });
    rejects((layout) => {
      layout.neighbors["paper-1"][0].id = "paper-1";
    });
  });

  it("requires the full cluster schema, thresholds, and membership", () => {
    rejects((layout) => {
      layout.cluster_method = "legacy" as never;
    });
    rejects((layout) => {
      layout.cluster_kind = "semantic regions" as never;
    });
    rejects((layout) => {
      delete (layout.cluster_quality as Partial<SemanticLayout["cluster_quality"]>)
        .silhouette_count;
    });
    rejects((layout) => {
      layout.cluster_quality.thresholds.stability_ari = 0.1 as never;
    });
    rejects((layout) => {
      layout.clusters[0].label_source = "heuristic" as never;
    });
    rejects((layout) => {
      layout.clusters[0].label_similarity = 0.2;
    });
    rejects((layout) => {
      layout.clusters[0].terms = ["one", "two", "three", "four", "five", "six"];
    });
    rejects((layout) => {
      layout.node_clusters["paper-1"] = "missing-cluster";
    });
    rejects((layout) => {
      layout.clusters[0].count -= 1;
    });
  });
});
