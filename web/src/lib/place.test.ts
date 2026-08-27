import { describe, expect, it } from "vitest";
import { makeAtlas, makeLayout } from "../test/fixtures";
import type { IdeaLayout } from "../types";
import { placeError } from "./place";

function fixture() {
  const atlas = makeAtlas({ layout: makeLayout() });
  const source = atlas.ideas[0];
  const idea = { ...structuredClone(source), id: "idea-derived" };
  atlas.ideas.push(idea);
  const layout: IdeaLayout = {
    schema_version: 1,
    method: "support-centroid-80-20-3d-v1",
    base_method: "embedding-umap-3d-v1",
    base_node_count: atlas.layout!.node_count,
    base_sha256: "a".repeat(64),
    input_sha256: "b".repeat(64),
    node_count: 1,
    positions: { [idea.id]: [100, 101, 102] },
    neighbors: { [idea.id]: ["paper-1", "topic:alignment"] },
    node_clusters: { [idea.id]: "cluster-one" },
  };
  return { atlas, layout };
}

describe("derived idea placement", () => {
  it("accepts a separate anchored visual overlay", () => {
    const { atlas, layout } = fixture();

    expect(placeError(layout, atlas.ideas, atlas.layout!)).toBeNull();
  });

  it("rejects unanchored placements", () => {
    const { atlas, layout } = fixture();
    layout.neighbors["idea-derived"] = ["missing"];
    expect(placeError(layout, atlas.ideas, atlas.layout!)).toBe(
      "invalid idea placement",
    );
  });
});
