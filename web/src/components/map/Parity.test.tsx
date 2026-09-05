import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { createCloud, isCloud, type CloudManifest } from "../../lib/cloud";
import type { RenderMode } from "../../hooks/webgl";
import { GraphControls } from "./Controls";

const PAPER_COUNT = 3_100_000;

function manifest(): CloudManifest {
  return {
    schema_version: 1,
    source: "arxiv",
    model: "all-minilm",
    model_digest: "a".repeat(64),
    model_revision: "b".repeat(40),
    projection: "anchor-cosine-8-v1",
    point_bytes: 13,
    source_count: PAPER_COUNT,
    count: PAPER_COUNT,
    counts: { likely: PAPER_COUNT, possible: 0, outside: 0 },
    omitted_count: 0,
    omitted_counts: { likely: 0, possible: 0, outside: 0 },
    omitted_sha256: "c".repeat(64),
    foreground_sha256: "d".repeat(64),
    shards: [
      {
        month: "2026-08",
        source_sha256: "e".repeat(64),
        source_count: PAPER_COUNT,
        source_counts: { likely: PAPER_COUNT, possible: 0, outside: 0 },
        foreground_sha256: "f".repeat(64),
        count: PAPER_COUNT,
        counts: { likely: PAPER_COUNT, possible: 0, outside: 0 },
        omitted_count: 0,
        omitted_counts: { likely: 0, possible: 0, outside: 0 },
        omitted_ids: [],
        omitted_sha256: "c".repeat(64),
        points: {
          path: "2026-08.bin",
          sha256: "1".repeat(64),
          bytes: 12 + PAPER_COUNT * 13,
        },
        meta: {
          path: "2026-08.json",
          sha256: "2".repeat(64),
          bytes: 1,
        },
      },
    ],
  };
}

function show(mode: RenderMode, count: number): string {
  return renderToStaticMarkup(
    <GraphControls count={count} layout="semantic" mode={mode} onReset={vi.fn()}>
      <span>tools</span>
    </GraphControls>,
  );
}

describe("renderer parity", () => {
  it("keeps all 3.1M papers across mode toggles", () => {
    const spec = manifest();
    expect(isCloud(spec)).toBe(true);
    const cloud = createCloud(spec);
    cloud.loaded = PAPER_COUNT;
    const states = (["2d", "3d", "2d"] as const).map((mode) =>
      show(mode, cloud.loaded),
    );

    expect(states.every((markup) => markup.includes("3,100,000 nodes"))).toBe(true);
    expect(states[0]).toContain("Compatibility · semantic frame");
    expect(states[1]).toContain("3D · semantic frame");
    expect(states[1]).not.toContain("Arrows select");
    expect(states[2]).toBe(states[0]);
  });
});
