import { describe, expect, it } from "vitest";
import {
  graphChrome,
  pickRegions,
  readClusters,
  viewRegions,
  type ClusterRegion,
  type RegionPoint,
} from "./clusters";

function makeRegion(id: string, count = 10): ClusterRegion {
  return {
    id,
    label: `Region ${id}`,
    centroid: [0, 0, 0],
    count,
    radius: 20,
    color: "#547861",
    terms: ["term"],
  };
}

function makePoint(id: string, x: number, y: number, count = 10): RegionPoint {
  return { region: makeRegion(id, count), x, y, depth: 0 };
}

describe("readClusters", () => {
  it("reads the generated cluster contract and normalizes labels", () => {
    const result = readClusters({
      clusters: [
        {
          id: "rl",
          label: "RL Environments",
          centroid: [1, 2, 3],
          count: 12,
          radius: 8,
          terms: ["World Models", "Search"],
        },
      ],
      node_clusters: { paper: "rl", invalid: 4 },
    });
    expect(result.regions[0]).toMatchObject({
      id: "rl",
      label: "rl environments",
      terms: ["world models", "search"],
    });
    expect(result.nodeClusters).toEqual({ paper: "rl" });
  });

  it("rejects malformed regions without failing the whole layout", () => {
    expect(
      readClusters({
        clusters: [null, { id: "bad", label: "bad", centroid: [1, 2] }],
      }).regions,
    ).toEqual([]);
  });
});

describe("viewRegions", () => {
  it("derives counts and centroids only from visible assigned nodes", () => {
    const source = makeRegion("a", 99);
    const result = viewRegions(
      { regions: [source, makeRegion("b", 50)], nodeClusters: { one: "a", two: "a" } },
      [
        { id: "one", x: 10, y: 20, z: 30 },
        { id: "two", x: 30, y: 40, z: 50 },
        { id: "unassigned", x: 1, y: 2, z: 3 },
      ],
    );
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ id: "a", count: 2, centroid: [20, 30, 40] });
  });

  it("returns no regions for an empty graph", () => {
    const source = makeRegion("a", 99);
    expect(
      viewRegions({ regions: [source], nodeClusters: { hidden: "a" } }, []),
    ).toEqual([]);
  });
});

describe("pickRegions", () => {
  it("caps overview labels and separates collisions", () => {
    const points = Array.from({ length: 12 }, (_, index) =>
      makePoint(String(index), 100 + index * 24, 120, 20 - index),
    );
    const result = pickRegions(points, { width: 1_200, height: 700, scale: 1 });
    expect(result.length).toBeLessThanOrEqual(6);
    expect(result.length).toBe(3);
  });

  it("shows fewer labels as the viewer moves closer", () => {
    const points = [
      makePoint("a", 100, 100),
      makePoint("b", 300, 100),
      makePoint("c", 500, 100),
      makePoint("d", 700, 100),
    ];
    expect(pickRegions(points, { width: 900, height: 600, scale: 1 })).toHaveLength(4);
    expect(pickRegions(points, { width: 900, height: 600, scale: 2.4 })).toHaveLength(
      1,
    );
    expect(pickRegions(points, { width: 900, height: 600, scale: 3.4 })).toHaveLength(
      0,
    );
  });

  it("never covers reserved selected-label space", () => {
    const points = [makePoint("blocked", 300, 200, 99), makePoint("safe", 600, 200)];
    const result = pickRegions(points, {
      width: 900,
      height: 500,
      scale: 1,
      reserved: [{ left: 230, right: 370, top: 170, bottom: 230 }],
    });
    expect(result.map((point) => point.region.id)).toEqual(["safe"]);
  });

  it("rejects points outside the visible 3D frame", () => {
    const result = pickRegions(
      [
        { ...makePoint("behind", 300, 200), depth: 2 },
        { ...makePoint("hidden", 500, 200), visible: false },
        makePoint("shown", 700, 200),
      ],
      { width: 900, height: 500, scale: 1 },
    );
    expect(result.map((point) => point.region.id)).toEqual(["shown"]);
  });

  it("keeps labels out of the graph controls", () => {
    const result = pickRegions(
      [makePoint("toolbar", 300, 60, 99), makePoint("safe", 500, 180)],
      { width: 900, height: 500, scale: 1 },
    );
    expect(result.map((point) => point.region.id)).toEqual(["safe"]);
  });

  it("can suppress regions for search, isolation, and connection views", () => {
    expect(
      pickRegions([makePoint("a", 300, 200)], {
        width: 900,
        height: 500,
        scale: 1,
        enabled: false,
      }),
    ).toEqual([]);
  });

  it("keeps labels below responsive graph controls without hiding safe labels", () => {
    const points = [
      makePoint("toolbar", 160, 170, 99),
      makePoint("safe", 160, 250, 10),
    ];
    const result = pickRegions(points, {
      width: 320,
      height: 500,
      scale: 1,
      reserved: graphChrome(320),
    });

    expect(result.map((point) => point.region.id)).toEqual(["safe"]);
  });
});
