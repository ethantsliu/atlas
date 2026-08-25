import { describe, expect, it } from "vitest";
import { qualityFor, showCluster, showLabel, showLink } from "./quality";

describe("adaptive quality", () => {
  it("uses full detail for a modest desktop constellation", () => {
    const quality = qualityFor({
      nodeCount: 111,
      width: 1440,
      height: 900,
      deviceMemory: 16,
      cores: 12,
      pixelRatio: 2,
    });

    expect(quality).toEqual({
      tier: "high",
      linkMode: "all",
      linkOpacity: 0.34,
      geometryDetail: 16,
      cooldownTicks: 150,
      pixelRatioCap: 2,
      labelMaxChars: 48,
      clusterMinNodes: 6,
      clusterMaxScale: 1.2,
    });
  });

  it("adapts the complete 2316-node graph on desktop", () => {
    const quality = qualityFor({
      nodeCount: 2_316,
      width: 1600,
      height: 1000,
      deviceMemory: 16,
      cores: 12,
      pixelRatio: 2,
    });

    expect(quality).toMatchObject({
      tier: "balanced",
      linkMode: "active",
      linkOpacity: 0.16,
      geometryDetail: 10,
      cooldownTicks: 80,
      pixelRatioCap: 1.5,
    });
  });

  it("selects the low-power phone profile for the full graph", () => {
    const quality = qualityFor({
      nodeCount: 2_319,
      width: 390,
      height: 700,
      deviceMemory: 4,
      cores: 4,
      pixelRatio: 3,
    });

    expect(quality).toMatchObject({
      tier: "low",
      linkMode: "active",
      linkOpacity: 0.16,
      geometryDetail: 6,
      cooldownTicks: 45,
      pixelRatioCap: 1,
    });
  });

  it("uses deterministic safe defaults when hardware hints are absent", () => {
    expect(qualityFor({ nodeCount: 111, width: 1440, height: 900 })).toMatchObject({
      tier: "high",
      geometryDetail: 16,
    });
    expect(qualityFor({ nodeCount: 2_319, width: 1440, height: 900 })).toMatchObject({
      tier: "balanced",
      linkMode: "active",
    });
  });

  it("shortens motion while preserving focused content", () => {
    const quality = qualityFor({
      nodeCount: 2_319,
      width: 390,
      height: 700,
      reducedMotion: true,
      deviceMemory: 4,
      cores: 4,
      pixelRatio: 3,
    });

    expect(quality.cooldownTicks).toBe(30);
    expect(showLabel()).toBe(false);
    expect(showLabel({ hovered: true })).toBe(true);
    expect(showLabel({ selected: true })).toBe(true);
    expect(showLabel({ keyboard: true })).toBe(true);
    expect(showLink(quality)).toBe(false);
    expect(showLink(quality, { selected: true })).toBe(true);
    expect(showLink(quality, { keyboard: true })).toBe(true);
  });

  it("keeps node labels interactive and cluster labels sparse", () => {
    const quality = qualityFor({
      nodeCount: 2_319,
      width: 1600,
      height: 1000,
      deviceMemory: 16,
      cores: 12,
    });

    expect(showLabel()).toBe(false);
    expect(showLabel({ hovered: true })).toBe(true);
    expect(showCluster(quality, quality.clusterMaxScale, 8)).toBe(false);
    expect(showCluster(quality, quality.clusterMaxScale, 9)).toBe(true);
    expect(showCluster(quality, quality.clusterMaxScale + 0.01, 20)).toBe(false);
  });
});
