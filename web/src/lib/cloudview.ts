export type CloudDetail = "sample" | "full";

export const CLOUD_LOD_CAP = 100_000;
export const CLOUD_LOD_MAX = 250_000;
export const CLOUD_STABLE_LIMIT = 3_000_000;
export const CLOUD_REST_MS = 160;
export const CLOUD_SETTLE_MS = 280;
export const CLOUD_LARGE_SETTLE_MS = 800;

export function cloudLod(count: number): number {
  if (count <= CLOUD_LOD_MAX) return Math.max(0, count);
  const floor = count >= CLOUD_STABLE_LIMIT ? CLOUD_LOD_CAP : 72_000;
  return Math.min(count, floor);
}

export function lodIds(count: number, sample = cloudLod(count)): Uint32Array {
  const size = Math.max(0, Math.min(count, Math.floor(sample)));
  const ids = new Uint32Array(size);
  for (let index = 0; index < size; index += 1) {
    ids[index] = Math.floor(((index + 0.5) * count) / size);
  }
  return ids;
}

export function cloudReduced(
  count: number,
  detail: CloudDetail,
  moving: boolean,
): boolean {
  if (detail === "full") return false;
  return moving || count >= CLOUD_STABLE_LIMIT;
}

export function cloudDrawCount(
  count: number,
  detail: CloudDetail,
  moving = false,
): number {
  return cloudReduced(count, detail, moving) ? cloudLod(count) : count;
}

export function cloudSettle(count: number, detail: CloudDetail = "sample"): number {
  const rendered = cloudDrawCount(count, detail);
  return rendered > CLOUD_LOD_MAX ? CLOUD_LARGE_SETTLE_MS : CLOUD_SETTLE_MS;
}

export function cloudSize(count: number): number {
  if (count >= 5_000_000) return 1;
  if (count >= 3_000_000) return 1.2;
  if (count >= 1_000_000) return 1.8;
  if (count >= 250_000) return 2.4;
  if (count >= 100_000) return 2.8;
  return 4.8;
}

export function cloudOpacity(count: number): number {
  if (count >= 5_000_000) return 0.24;
  if (count >= 3_000_000) return 0.3;
  if (count >= 1_000_000) return 0.42;
  if (count >= 250_000) return 0.6;
  if (count >= 100_000) return 0.78;
  return 0.96;
}

export type CloudTone = { opacity: number; size: number };

export function cloudTone(count: number): CloudTone {
  return { opacity: cloudOpacity(count), size: cloudSize(count) };
}

export function motionTone(count: number): CloudTone {
  const base = cloudTone(count);
  const sample = Math.max(1, cloudLod(count));
  if (sample >= count) return base;
  const density = Math.max(1, count / sample);
  const sizeScale = Math.min(2.2, density ** 0.25);
  const alphaScale = Math.min(1.65, density ** 0.15);
  return {
    opacity: Math.min(Math.max(base.opacity, 0.72), base.opacity * alphaScale),
    size: Math.min(Math.max(base.size, 3.4), base.size * sizeScale),
  };
}
