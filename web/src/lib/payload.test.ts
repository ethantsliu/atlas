import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { makeAtlas, makeLayout } from "../test/fixtures";
import type { Atlas, SemanticLayout } from "../types";
import {
  type AtlasCore,
  type LegacyPaperBundle,
  type PaperBundle,
  bundleError,
  coreError,
  mergeAtlas,
  stageAtlas,
} from "./payload";

function splitAtlas(atlas: Atlas): { core: AtlasCore; bundle: PaperBundle } {
  if (!atlas.layout) throw new Error("Test atlas requires a layout");
  const { papers, ...rest } = atlas;
  const paperIds = new Set(papers.map((paper) => paper.id));
  const coreLayout = { ...atlas.layout };
  const paperLayout: NonNullable<PaperBundle["layout"]> = {
    positions: {},
    neighbors: {},
    node_clusters: {},
  };
  for (const field of ["positions", "neighbors", "node_clusters"] as const) {
    const values = (atlas.layout as unknown as Record<string, unknown> | undefined)?.[
      field
    ];
    if (typeof values !== "object" || values == null || Array.isArray(values)) continue;
    const entries = Object.entries(values);
    (coreLayout as unknown as Record<string, unknown>)[field] = Object.fromEntries(
      entries.filter(([id]) => !paperIds.has(id)),
    );
    (paperLayout as unknown as Record<string, unknown>)[field] = Object.fromEntries(
      entries.filter(([id]) => paperIds.has(id)),
    );
  }
  const bundle: PaperBundle = {
    schema_version: 2,
    papers,
    ideas: [],
    idea_layout: null,
    layout: paperLayout,
  };
  const content = `${JSON.stringify(bundle)}\n`;
  const digest = createHash("sha256").update(content).digest("hex");
  const core = {
    schema_version: 2,
    ...rest,
    layout: coreLayout,
    paper_asset: {
      schema_version: 1,
      path: `/data/papers/${digest}.json`,
      sha256: digest,
      bytes: new TextEncoder().encode(content).byteLength,
      paper_count: papers.length,
    },
  } as unknown as AtlasCore;
  return { core, bundle };
}

describe("split payload contracts", () => {
  it("reconstructs the committed static split with browser validators", () => {
    const core = JSON.parse(
      readFileSync(new URL("../../public/data/atlas.json", import.meta.url), "utf8"),
    ) as AtlasCore;
    const bundle = JSON.parse(
      readFileSync(
        new URL(`../../public${core.paper_asset.path}`, import.meta.url),
        "utf8",
      ),
    ) as PaperBundle;

    expect(coreError(core)).toBeNull();
    expect(bundleError(bundle, core.paper_asset)).toBeNull();
    const merged = mergeAtlas(core, bundle);
    expect(merged.papers).toHaveLength(core.meta.paper_count);
  });

  it("validates a map-first core and reconstructs the authoritative atlas", () => {
    const atlas = makeAtlas({
      layout: makeLayout(),
    });
    const { core, bundle } = splitAtlas(atlas);

    expect(coreError(core)).toBeNull();
    expect(bundleError(bundle, core.paper_asset)).toBeNull();
    expect(stageAtlas(core).papers).toEqual([]);
    expect(mergeAtlas(core, bundle)).toEqual(atlas);

    bundle.layout!.positions!["topic:alignment"] = [9, 9, 9];
    expect(() => mergeAtlas(core, bundle)).toThrow("overlaps core");
  });

  it("accepts cached schema v1 paper bundles without changing the v2 type", () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const { core, bundle } = splitAtlas(atlas);
    const legacy: LegacyPaperBundle = {
      schema_version: 1,
      papers: bundle.papers,
      layout: bundle.layout,
    };

    expect(bundleError(legacy, core.paper_asset)).toBeNull();
    expect(mergeAtlas(core, legacy)).toEqual(atlas);
    expect(bundleError({ ...legacy, ideas: [] }, core.paper_asset)).toBe(
      "invalid paper bundle contract",
    );
  });

  it("binds the asset path, digest, byte count, and paper count", () => {
    const { core, bundle } = splitAtlas(makeAtlas({ layout: makeLayout() }));
    const wrongDigest = {
      ...core,
      paper_asset: { ...core.paper_asset, sha256: "0".repeat(64) },
    };
    expect(coreError(wrongDigest)).toBe("invalid paper asset contract");

    const wrongCount = { ...bundle, papers: bundle.papers.slice(1) };
    expect(bundleError(wrongCount, core.paper_asset)).toBe(
      "invalid paper bundle contract",
    );
  });

  it("rejects incomplete or semantically invalid layout shards", () => {
    const { core, bundle } = splitAtlas(makeAtlas({ layout: makeLayout() }));

    const absent = structuredClone(bundle) as Partial<PaperBundle>;
    delete absent.layout;
    expect(() => mergeAtlas(core, absent as PaperBundle)).toThrow("shard is missing");

    const missingMap = structuredClone(bundle);
    delete (missingMap.layout as Partial<NonNullable<PaperBundle["layout"]>>).neighbors;
    expect(bundleError(missingMap, core.paper_asset)).toBe(
      "invalid paper bundle contract",
    );

    const missingPaper = structuredClone(bundle);
    delete missingPaper.layout!.positions["paper-1"];
    expect(bundleError(missingPaper, core.paper_asset)).toBe(
      "invalid paper bundle contract",
    );

    const extraCore = structuredClone(core);
    extraCore.layout!.positions["paper-1"] = [0, 0, 0];
    expect(coreError(extraCore)).toBe("incomplete semantic layout maps");

    const badOrder = structuredClone(bundle);
    badOrder.layout!.neighbors["paper-1"][1].score = 0.95;
    expect(() => mergeAtlas(core, badOrder)).toThrow("invalid semantic neighbor");

    const badTarget = structuredClone(bundle);
    badTarget.layout!.neighbors["paper-1"][0].id = "missing-node";
    expect(() => mergeAtlas(core, badTarget)).toThrow("invalid semantic neighbor");

    const badCluster = structuredClone(bundle);
    badCluster.layout!.node_clusters["paper-1"] = "missing-cluster";
    expect(() => mergeAtlas(core, badCluster)).toThrow("unknown cluster assignment");
  });

  it("defers paper evidence semantics until the full bundle is present", () => {
    const core = JSON.parse(
      readFileSync(new URL("../../public/data/atlas.json", import.meta.url), "utf8"),
    ) as AtlasCore;
    const bundle = JSON.parse(
      readFileSync(
        new URL(`../../public${core.paper_asset.path}`, import.meta.url),
        "utf8",
      ),
    ) as PaperBundle;
    const idea = core.ideas.find((item) => item.brief.status === "researched-draft");
    expect(idea).toBeDefined();
    idea!.brief.paper_ids = ["arxiv:missing-paper"];
    delete idea!.brief.reading_roles;

    expect(coreError(core)).toBeNull();
    expect(() => mergeAtlas(core, bundle)).toThrow("Merged atlas has an invalid shape");
  });

  it("rejects malformed core content before first paint", () => {
    const { core } = splitAtlas(makeAtlas({ layout: makeLayout() }));
    const unknownRoute = structuredClone(core);
    unknownRoute.ideas[0].topic_ids = ["private-route"];
    expect(coreError(unknownRoute)).toBe("unknown idea taxonomy reference");

    const personal = { ...core, personal_sources: [] };
    expect(coreError(personal)).toBe("invalid core shape");

    const duplicate = structuredClone(core);
    duplicate.topics.push(structuredClone(duplicate.topics[0]));
    expect(coreError(duplicate)).toBe("duplicate core graph node IDs");

    const oldLayout = structuredClone(core);
    oldLayout.layout.schema_version = 2 as never;
    expect(coreError(oldLayout)).toBe("invalid semantic layout contract");

    const oldText = structuredClone(core);
    oldText.layout.embedding.text_schema = "legacy" as never;
    expect(coreError(oldText)).toBe("invalid embedding provenance");

    const aliases = structuredClone(core);
    aliases.layout.quality.alias_policy = "include aliases" as never;
    expect(coreError(aliases)).toBe("invalid layout quality");

    const incompleteQuality = structuredClone(core);
    delete (
      incompleteQuality.layout.cluster_quality as Partial<
        SemanticLayout["cluster_quality"]
      >
    ).silhouette_count;
    expect(coreError(incompleteQuality)).toBe("invalid semantic clusters");
  });
});
