import { describe, expect, it } from "vitest";
import { qualityFor, showLink } from "./quality";

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
      geometryDetail: 6,
      cooldownTicks: 80,
      pixelRatioCap: 1,
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

  it("reduces only canvas resolution for million-point archives", () => {
    const quality = qualityFor({
      nodeCount: 3_145_393,
      width: 1_440,
      height: 800,
      deviceMemory: 16,
      cores: 12,
      pixelRatio: 2,
    });

    expect(quality.pixelRatioCap).toBe(0.75);
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
    expect(showLink(quality)).toBe(false);
    expect(showLink(quality, { selected: true })).toBe(true);
    expect(showLink(quality, { keyboard: true })).toBe(true);
  });
});
