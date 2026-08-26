import { describe, expect, it } from "vitest";
import {
  ALL_NODE_KINDS,
  buildGraph,
  graphEndpointId,
  largestGroup,
  splitPapers,
  stableGraph,
} from "./graph";
import { makeAtlas, makeIdea, makeLayout, makePaper } from "../test/fixtures";
import type { GraphNodeKind } from "../types";

function allKinds(): Set<GraphNodeKind> {
  return new Set(ALL_NODE_KINDS);
}

describe("buildGraph", () => {
  it("removes infeasible ideas and every dangling link", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: allKinds(),
      focus: null,
      query: "",
      minFeasibility: 5,
    });

    expect(graph.nodes.map((node) => node.id)).toContain("idea-high");
    expect(graph.nodes.map((node) => node.id)).not.toContain("idea-low");
    expect(graph.links.length).toBeGreaterThan(3);
    expect(
      graph.links.every(
        (link) =>
          graph.nodes.some((node) => node.id === graphEndpointId(link.source)) &&
          graph.nodes.some((node) => node.id === graphEndpointId(link.target)),
      ),
    ).toBe(true);
  });

  it("honors enabled node kinds", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: new Set<GraphNodeKind>(["topic", "idea"]),
      focus: null,
      query: "",
      minFeasibility: 1,
    });

    expect(new Set(graph.nodes.map((node) => node.kind))).toEqual(
      new Set(["topic", "idea"]),
    );
    expect(graph.links.every((link) => link.kind === "topic")).toBe(true);
  });

  it("isolates a node and its immediate neighborhood", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: allKinds(),
      focus: "idea-high",
      query: "",
      minFeasibility: 1,
    });

    expect(new Set(graph.nodes.map((node) => node.id))).toEqual(
      new Set(["idea-high", "paper-1", "topic:alignment", "trick:variance-control"]),
    );
  });

  it("matches labels case-insensitively and includes direct neighbors", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: allKinds(),
      focus: null,
      query: "  ALIGNMENT signals  ",
      minFeasibility: 1,
    });

    expect(new Set(graph.nodes.map((node) => node.id))).toEqual(
      new Set(["paper-1", "idea-high", "topic:alignment", "trick:variance-control"]),
    );
  });

  it("finds a paper without enabling the persistent paper lens", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: new Set<GraphNodeKind>(["topic", "trick", "idea"]),
      focus: null,
      query: "alignment signals",
      minFeasibility: 1,
    });

    expect(graph.nodes.find((node) => node.id === "paper-1")?.kind).toBe("paper");
  });

  it("retains one selected paper while its lens is off", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: new Set<GraphNodeKind>(["topic", "trick", "idea"]),
      focus: null,
      selected: "paper-1",
      query: "",
      minFeasibility: 1,
    });

    expect(graph.nodes.find((node) => node.id === "paper-1")?.kind).toBe("paper");
  });

  it("returns an empty graph when no label matches", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: allKinds(),
      focus: null,
      query: "missing phrase",
      minFeasibility: 1,
    });

    expect(graph).toEqual({ nodes: [], links: [] });
  });

  it("makes every corpus paper available as an optional graph node", () => {
    const atlas = makeAtlas();
    const withPapers = buildGraph(atlas, {
      kinds: new Set<GraphNodeKind>(["paper"]),
      focus: null,
      query: "",
      minFeasibility: 1,
    });
    expect(withPapers.nodes.map((node) => node.id)).toEqual(
      atlas.papers.map((paper) => paper.id),
    );
  });

  it("starts nodes at their semantic embedding coordinates", () => {
    const atlas = makeAtlas();
    atlas.layout = makeLayout();
    atlas.layout.positions["paper-1"] = [12, -8, 4];
    const graph = buildGraph(atlas, {
      kinds: new Set<GraphNodeKind>(["paper"]),
      focus: null,
      query: "",
      minFeasibility: 1,
    });

    expect(graph.nodes.find((node) => node.id === "paper-1")).toMatchObject({
      x: 12,
      y: -8,
      z: 4,
      sx: 12,
      sy: -8,
      sz: 4,
    });
  });

  it("sizes reviewed papers from reading depth without loading detail bodies", () => {
    const atlas = makeAtlas();
    atlas.papers[0].reading_depth = "verified";
    atlas.papers[0].full_reading_path =
      "/data/readings/arxiv-0001-00001--0123456789ab-fedcba987654.json";
    const graph = buildGraph(atlas, {
      kinds: new Set<GraphNodeKind>(["paper"]),
      focus: null,
      query: "",
      minFeasibility: 1,
    });

    expect(graph.nodes.find((node) => node.id === "paper-1")?.val).toBe(4.5);
  });

  it("connects work packages directly to their parent program", () => {
    const atlas = makeAtlas();
    atlas.ideas = [
      makeIdea({ id: "program", portfolio_role: "program" }),
      makeIdea({
        id: "validator",
        portfolio_role: "work-package",
        parent_idea_id: "program",
      }),
    ];

    const graph = buildGraph(atlas, {
      kinds: new Set<GraphNodeKind>(["idea"]),
      focus: "validator",
      query: "",
      minFeasibility: 1,
    });

    expect(new Set(graph.nodes.map((node) => node.id))).toEqual(
      new Set(["program", "validator"]),
    );
    expect(graph.links).toContainEqual({
      source: "validator",
      target: "program",
      kind: "idea",
    });
  });

  it("links every duplicate collection paper", () => {
    const atlas = makeAtlas();
    atlas.papers.push(
      makePaper({
        id: "paper-duplicate",
        stable_id: atlas.papers[0].stable_id,
      }),
    );

    const graph = buildGraph(atlas, {
      kinds: new Set<GraphNodeKind>(["paper", "idea"]),
      focus: null,
      query: "",
      minFeasibility: 1,
    });
    const targets = graph.links
      .filter((link) => graphEndpointId(link.source) === "idea-high")
      .map((link) => graphEndpointId(link.target));

    expect(targets).toContain("paper-1");
    expect(targets).toContain("paper-duplicate");
  });

  it("never leaves a higher-scored work package orphaned by the threshold", () => {
    const atlas = makeAtlas();
    const program = makeIdea({ id: "program", portfolio_role: "program" });
    const workPackage = makeIdea({
      id: "validator",
      portfolio_role: "work-package",
      parent_idea_id: program.id,
    });
    program.feasibility.score = 6.1;
    workPackage.feasibility.score = 6.6;
    atlas.ideas = [program, workPackage];

    const graph = buildGraph(atlas, {
      kinds: new Set<GraphNodeKind>(["idea"]),
      focus: null,
      query: "",
      minFeasibility: 6.5,
    });

    expect(graph).toEqual({ nodes: [], links: [] });
  });
});

describe("largestGroup", () => {
  it("finds the main connected constellation", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: allKinds(),
      focus: null,
      query: "",
      minFeasibility: 1,
    });
    graph.nodes.push({
      ...graph.nodes[0],
      id: "isolated",
      label: "Isolated node",
    });

    const group = largestGroup(graph);
    expect(group.size).toBeGreaterThan(1);
    expect(group.has("isolated")).toBe(false);
  });
});

describe("splitPapers", () => {
  it("batches every paper without leaving paper links in the core graph", () => {
    const graph = buildGraph(makeAtlas(), {
      kinds: allKinds(),
      focus: null,
      query: "",
      minFeasibility: 1,
    });
    const split = splitPapers(graph);
    const paperIds = new Set(split.papers.map((node) => node.id));

    expect(split.papers.every((node) => node.kind === "paper")).toBe(true);
    expect(split.core.nodes.every((node) => node.kind !== "paper")).toBe(true);
    expect(
      split.core.links.every(
        (link) =>
          !paperIds.has(graphEndpointId(link.source)) &&
          !paperIds.has(graphEndpointId(link.target)),
      ),
    ).toBe(true);
  });
});

describe("stableGraph", () => {
  it("retains renderer identity and live coordinates across graph updates", () => {
    const cache = new Map();
    const first = stableGraph(
      buildGraph(makeAtlas(), {
        kinds: allKinds(),
        focus: null,
        query: "",
        minFeasibility: 1,
      }),
      cache,
    );
    const node = first.nodes.find((item) => item.id === "topic:alignment")!;
    node.x = 999;
    const second = stableGraph(
      buildGraph(makeAtlas(), {
        kinds: allKinds(),
        focus: null,
        query: "alignment",
        minFeasibility: 1,
      }),
      cache,
    );
    const retained = second.nodes.find((item) => item.id === node.id);

    expect(retained).toBe(node);
    expect(retained?.x).toBe(999);
  });
});
