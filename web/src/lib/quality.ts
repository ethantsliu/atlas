export type QualityTier = "high" | "balanced" | "low";
export type LinkMode = "all" | "active";

export type QualityInput = {
  nodeCount: number;
  width: number;
  height: number;
  reducedMotion?: boolean;
  deviceMemory?: number;
  cores?: number;
  pixelRatio?: number;
};

export type QualityProfile = {
  tier: QualityTier;
  linkMode: LinkMode;
  linkOpacity: number;
  geometryDetail: 6 | 10 | 16;
  cooldownTicks: number;
  pixelRatioCap: number;
};

export type FocusState = {
  selected?: boolean;
  keyboard?: boolean;
  hovered?: boolean;
};

const PROFILES: Record<QualityTier, Omit<QualityProfile, "tier">> = {
  high: {
    linkMode: "all",
    linkOpacity: 0.34,
    geometryDetail: 16,
    cooldownTicks: 150,
    pixelRatioCap: 2,
  },
  balanced: {
    linkMode: "all",
    linkOpacity: 0.22,
    geometryDetail: 10,
    cooldownTicks: 80,
    pixelRatioCap: 1.5,
  },
  low: {
    linkMode: "active",
    linkOpacity: 0.16,
    geometryDetail: 6,
    cooldownTicks: 45,
    pixelRatioCap: 1,
  },
};

function safeNumber(value: number | undefined, fallback: number): number {
  return Number.isFinite(value) && value! > 0 ? value! : fallback;
}

function qualityScore(input: QualityInput): number {
  const nodes = Math.max(0, input.nodeCount);
  const area = Math.max(1, input.width) * Math.max(1, input.height);
  const memory = safeNumber(input.deviceMemory, 8);
  const cores = safeNumber(input.cores, 8);
  const ratio = safeNumber(input.pixelRatio, 1);
  let score = nodes >= 1_800 ? 2 : nodes >= 800 ? 1 : 0;

  score += area < 400_000 ? 2 : area < 800_000 ? 1 : 0;
  score += memory <= 4 ? 2 : memory <= 6 ? 1 : 0;
  score += cores <= 4 ? 2 : cores <= 6 ? 1 : 0;
  score += ratio > 2 ? 1 : 0;
  score += input.reducedMotion ? 2 : 0;
  return score;
}

function qualityTier(input: QualityInput): QualityTier {
  const score = qualityScore(input);
  if (score >= 6) return "low";
  if (score >= 2) return "balanced";
  return "high";
}

export function qualityFor(input: QualityInput): QualityProfile {
  const tier = qualityTier(input);
  const base = PROFILES[tier];
  const dense = input.nodeCount >= 1_800;
  const archive = input.nodeCount >= 1_000_000;
  return {
    ...base,
    tier,
    linkMode: dense ? "active" : base.linkMode,
    linkOpacity: dense ? Math.min(base.linkOpacity, 0.16) : base.linkOpacity,
    geometryDetail: dense ? 6 : base.geometryDetail,
    pixelRatioCap: archive
      ? Math.min(base.pixelRatioCap, 0.75)
      : dense
        ? Math.min(base.pixelRatioCap, 1)
        : base.pixelRatioCap,
    cooldownTicks: input.reducedMotion
      ? Math.min(base.cooldownTicks, 30)
      : base.cooldownTicks,
  };
}

export function showLink(
  profile: QualityProfile,
  state: Pick<FocusState, "selected" | "keyboard"> = {},
): boolean {
  return profile.linkMode === "all" || Boolean(state.selected || state.keyboard);
}
