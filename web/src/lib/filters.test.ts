import { describe, expect, it } from "vitest";
import {
  filterIdeaQuery,
  filterPaperTitles,
  findPaperIds,
  findNodePapers,
  resolvePaper,
  sortIdeaScores,
} from "./filters";
import { buildGraph, ALL_NODE_KINDS } from "./graph";
import { makeAtlas } from "../test/fixtures";

describe("title filters", () => {
  const atlas = makeAtlas();

  it("filters paper titles without case or surrounding-space sensitivity", () => {
    expect(filterPaperTitles(atlas.papers, "  MODEL search ")).toEqual([
      atlas.papers[1],
    ]);
  });

  it("returns a new complete list for an empty query", () => {
    const result = filterIdeaQuery(atlas.ideas, "   ");
    expect(result).toEqual(atlas.ideas);
    expect(result).not.toBe(atlas.ideas);
  });

  it("searches idea concepts and prose", () => {
    expect(filterIdeaQuery(atlas.ideas, "world models")).toEqual([atlas.ideas[1]]);
    expect(filterIdeaQuery(atlas.ideas, "thesis")).toEqual(atlas.ideas);
    expect(filterIdeaQuery(atlas.ideas, "variance control")).toEqual([atlas.ideas[0]]);
  });

  it("sorts feasibility without mutating source order", () => {
    const source = [...atlas.ideas].reverse();
    expect(sortIdeaScores(source).map((idea) => idea.id)).toEqual([
      "idea-high",
      "idea-low",
    ]);
    expect(source.map((idea) => idea.id)).toEqual(["idea-low", "idea-high"]);
  });

  it("resolves exact and unique stable paper IDs", () => {
    expect(resolvePaper(atlas.papers, atlas.papers[0].id)).toBe(atlas.papers[0]);
    expect(resolvePaper(atlas.papers, atlas.papers[1].stable_id!)).toBe(
      atlas.papers[1],
    );
    expect(resolvePaper(atlas.papers, "missing")).toBeNull();
  });
});

describe("paper resolution", () => {
  const atlas = makeAtlas();

  it("resolves both local and stable paper IDs without duplicates", () => {
    expect(
      findPaperIds(atlas.papers, ["paper-1", "arxiv:0001.00001", "arxiv:0002.00002"]),
    ).toEqual(atlas.papers);
  });

  it("finds routed papers for a graph node", () => {
    const graph = buildGraph(atlas, {
      kinds: new Set(ALL_NODE_KINDS),
      focus: null,
      query: "",
      minFeasibility: 1,
    });
    const alignment = graph.nodes.find((node) => node.id === "topic:alignment");

    expect(alignment).toBeDefined();
    expect(findNodePapers(alignment!, atlas.papers)).toEqual([atlas.papers[0]]);
  });
});
