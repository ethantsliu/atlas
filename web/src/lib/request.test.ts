import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas, makeLayout } from "../test/fixtures";
import type { Atlas } from "../types";
import { fetchPapers } from "./paper";
import type { AtlasCore, LegacyPaperBundle, PaperBundle } from "./payload";
import { basePath } from "./paths";
import * as placement from "./place";
import { fetchAtlas, fetchCore } from "./request";

function splitAtlas(atlas: Atlas): {
  core: AtlasCore;
  bundle: PaperBundle;
  bytes: Uint8Array;
} {
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
  const bytes = new TextEncoder().encode(`${JSON.stringify(bundle)}\n`);
  const digest = createHash("sha256").update(bytes).digest("hex");
  const core = {
    schema_version: 2,
    ...rest,
    layout: coreLayout,
    paper_asset: {
      schema_version: 1,
      path: `/data/papers/${digest}.json`,
      sha256: digest,
      bytes: bytes.byteLength,
      paper_count: papers.length,
    },
  } as unknown as AtlasCore;
  return { core, bundle, bytes };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function splitFetcher(atlas: Atlas) {
  const split = splitAtlas(atlas);
  const fetcher = vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("atlas.json")
      ? jsonResponse(split.core)
      : new Response(split.bytes.buffer as ArrayBuffer),
  ) as unknown as typeof fetch;
  return { ...split, fetcher };
}

describe("atlas requests", () => {
  it("loads only the revalidated core until papers are requested", async () => {
    const { core, fetcher } = splitFetcher(makeAtlas({ layout: makeLayout() }));
    const controller = new AbortController();

    await expect(fetchCore(controller.signal, fetcher)).resolves.toEqual(core);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(basePath("/data/atlas.json"), {
      signal: controller.signal,
      cache: "no-cache",
    });
  });

  it("verifies and reconstructs the complete atlas on demand", async () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const { core, fetcher } = splitFetcher(atlas);
    const signal = new AbortController().signal;

    await expect(fetchPapers(core, signal, fetcher)).resolves.toEqual(atlas);
    expect(fetcher).toHaveBeenCalledWith(basePath(core.paper_asset.path), {
      signal,
      cache: "force-cache",
    });
  });

  it("reconstructs a cached core that references a schema v1 paper bundle", async () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const { core, bundle } = splitAtlas(atlas);
    const legacy: LegacyPaperBundle = {
      schema_version: 1,
      papers: bundle.papers,
      layout: bundle.layout,
    };
    const bytes = new TextEncoder().encode(`${JSON.stringify(legacy)}\n`);
    const digest = createHash("sha256").update(bytes).digest("hex");
    const legacyCore: AtlasCore = {
      ...core,
      paper_asset: {
        ...core.paper_asset,
        path: `/data/papers/${digest}.json`,
        sha256: digest,
        bytes: bytes.byteLength,
      },
    };
    const fetcher = vi.fn(
      async () => new Response(bytes.buffer as ArrayBuffer),
    ) as unknown as typeof fetch;

    await expect(
      fetchPapers(legacyCore, new AbortController().signal, fetcher),
    ).resolves.toEqual(atlas);
  });

  it("retains an eager compatibility request that reconstructs exact data", async () => {
    const atlas = makeAtlas({
      layout: makeLayout(),
    });
    const { fetcher } = splitFetcher(atlas);

    await expect(fetchAtlas(new AbortController().signal, fetcher)).resolves.toEqual(
      atlas,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("rejects HTTP failures and malformed core bodies", async () => {
    const failed = vi.fn(async () =>
      jsonResponse(null, 503),
    ) as unknown as typeof fetch;
    await expect(fetchCore(new AbortController().signal, failed)).rejects.toThrow(
      "Atlas request failed (503)",
    );

    const malformed = vi.fn(async () =>
      jsonResponse({ meta: {}, papers: [] }),
    ) as unknown as typeof fetch;
    await expect(fetchCore(new AbortController().signal, malformed)).rejects.toThrow(
      "Atlas core has an invalid shape",
    );
  });

  it("rejects paper bytes that disagree with immutable metadata", async () => {
    const { core } = splitAtlas(makeAtlas({ layout: makeLayout() }));
    const fetcher = vi.fn(async () => new Response("{}\n")) as unknown as typeof fetch;

    await expect(
      fetchPapers(core, new AbortController().signal, fetcher),
    ).rejects.toThrow("byte length does not match");
  });

  it("screens derived placements after the full asset is merged", async () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const { core, fetcher } = splitFetcher(atlas);
    vi.spyOn(placement, "placeError").mockReturnValueOnce("invalid idea placement");

    await expect(
      fetchPapers(core, new AbortController().signal, fetcher),
    ).rejects.toThrow("invalid idea placement");
  });

  it("rejects same-length paper bytes with the wrong digest", async () => {
    const { core, bytes } = splitAtlas(makeAtlas({ layout: makeLayout() }));
    const corrupted = bytes.slice();
    corrupted[corrupted.length - 2] ^= 1;
    const fetcher = vi.fn(
      async () => new Response(corrupted.buffer as ArrayBuffer),
    ) as unknown as typeof fetch;

    await expect(
      fetchPapers(core, new AbortController().signal, fetcher),
    ).rejects.toThrow("digest does not match");
  });

  it("honors the configured deployment base for both assets", async () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const { core, fetcher } = splitFetcher(atlas);
    const signal = new AbortController().signal;

    await fetchAtlas(signal, fetcher, "/atlas/");

    expect(fetcher).toHaveBeenNthCalledWith(1, "/atlas/data/atlas.json", {
      signal,
      cache: "no-cache",
    });
    expect(fetcher).toHaveBeenNthCalledWith(2, `/atlas${core.paper_asset.path}`, {
      signal,
      cache: "force-cache",
    });
  });
});
