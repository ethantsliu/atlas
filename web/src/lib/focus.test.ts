import { describe, expect, it } from "vitest";
import { makeAtlas, makeLayout } from "../test/fixtures";
import type { CloudData, CloudPick } from "./cloud";
import { focusCloud } from "./focus";

describe("focusCloud", () => {
  it("pins exact anchor routes around one historical paper", () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const cloud: CloudData = {
      positions: new Float32Array([12, 13, 14]),
      scopes: new Uint8Array([0]),
      ranges: [],
    };
    const pick: CloudPick = {
      index: 0,
      paper: {
        id: "2001.00001",
        title: "Historical",
        url: "https://arxiv.org/abs/2001.00001",
        published: "2020-01-01",
        scope: "likely",
      },
    };
    const result = focusCloud(atlas, cloud, pick, {
      neighbors: [
        { id: "topic:alignment", score: 0.8 },
        { id: "paper-1", score: 0.7 },
      ],
    });

    expect(result?.mark.center).toEqual([12, 13, 14]);
    expect(result?.graph.nodes.map((node) => node.id)).toEqual([
      "topic:alignment",
      "paper-1",
    ]);
    expect(result?.graph.nodes.every((node) => node.fx === node.x)).toBe(true);
    expect(result?.mark.targets.map((target) => target.score)).toEqual([0.8, 0.7]);
  });

  it("fails closed when a route target is absent", () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const cloud: CloudData = {
      positions: new Float32Array([1, 2, 3]),
      scopes: new Uint8Array([0]),
      ranges: [],
    };
    const pick = {
      index: 0,
      paper: {
        id: "2001.00001",
        title: "Historical",
        url: "https://arxiv.org/abs/2001.00001",
        published: "2020-01-01",
        scope: "likely" as const,
      },
    };

    expect(
      focusCloud(atlas, cloud, pick, {
        neighbors: [{ id: "missing", score: 0.8 }],
      }),
    ).toBeNull();
  });
});
