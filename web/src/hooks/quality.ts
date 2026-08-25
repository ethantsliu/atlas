import { useEffect, useMemo, useState } from "react";
import { qualityFor, type QualityProfile } from "../lib/quality";

type DeviceNav = Navigator & { deviceMemory?: number };

function motionQuery(): MediaQueryList | null {
  if (typeof window === "undefined" || !window.matchMedia) return null;
  return window.matchMedia("(prefers-reduced-motion: reduce)");
}

function readMotion(): boolean {
  return motionQuery()?.matches ?? false;
}

export function useQuality(
  nodeCount: number,
  width: number,
  height: number,
): QualityProfile {
  const [reducedMotion, setMotion] = useState(readMotion);

  useEffect(() => {
    const query = motionQuery();
    if (!query) return;
    const sync = () => setMotion(query.matches);
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return useMemo(() => {
    const nav = typeof navigator === "undefined" ? undefined : (navigator as DeviceNav);
    const pixelRatio = typeof window === "undefined" ? 1 : window.devicePixelRatio;
    return qualityFor({
      nodeCount,
      width,
      height,
      reducedMotion,
      deviceMemory: nav?.deviceMemory,
      cores: nav?.hardwareConcurrency,
      pixelRatio,
    });
  }, [height, nodeCount, reducedMotion, width]);
}
