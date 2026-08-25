export type Point3 = readonly [number, number, number];

export type ClusterRegion = {
  id: string;
  label: string;
  centroid: Point3;
  count: number;
  radius: number;
  color: string;
  terms: readonly string[];
};

export type ClusterSet = {
  regions: ClusterRegion[];
  nodeClusters: Readonly<Record<string, string>>;
};

export type RegionPoint = {
  region: ClusterRegion;
  x: number;
  y: number;
  depth: number;
  visible?: boolean;
};

export type RegionBox = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type RegionView = {
  width: number;
  height: number;
  scale: number;
  enabled?: boolean;
  activeId?: string | null;
  reserved?: readonly RegionBox[];
  limit?: number;
};

export type VisibleRegion = RegionPoint & {
  opacity: number;
};

export type ClusterNode = {
  id: string;
  x?: number;
  y?: number;
  z?: number;
};

/** Screen space occupied by persistent graph controls above the plotted field. */
export function graphChrome(width: number): RegionBox[] {
  if (width <= 0) return [];
  const bottom = width <= 480 ? 176 : width <= 720 ? 130 : 88;
  return [{ left: 0, right: width, top: 0, bottom }];
}

const colors = [
  "#547861",
  "#806b54",
  "#547083",
  "#8a5f67",
  "#70658a",
  "#727949",
  "#4f7b79",
  "#8b6947",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readPoint(value: unknown): Point3 | null {
  if (!Array.isArray(value) || value.length !== 3) return null;
  if (!value.every((part) => typeof part === "number" && Number.isFinite(part))) {
    return null;
  }
  return [value[0], value[1], value[2]];
}

function readTerms(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((term): term is string => typeof term === "string")
    .map((term) => term.trim().toLocaleLowerCase())
    .filter(Boolean)
    .slice(0, 4);
}

function colorFor(id: string): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  return colors[Math.abs(hash) % colors.length];
}

function readRegion(value: unknown): ClusterRegion | null {
  if (!isRecord(value) || typeof value.id !== "string") return null;
  const centroid = readPoint(value.centroid);
  if (!centroid) return null;
  const label = typeof value.label === "string" ? value.label.trim() : "";
  const count = typeof value.count === "number" ? Math.max(0, value.count) : 0;
  const radius = typeof value.radius === "number" ? Math.max(0, value.radius) : 0;
  if (!label || !Number.isFinite(count) || !Number.isFinite(radius)) return null;
  return {
    id: value.id,
    label: label.toLocaleLowerCase(),
    centroid,
    count,
    radius,
    color: typeof value.color === "string" ? value.color : colorFor(value.id),
    terms: readTerms(value.terms),
  };
}

function readMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

export function readClusters(layout: unknown): ClusterSet {
  if (!isRecord(layout)) return { regions: [], nodeClusters: {} };
  const source = Array.isArray(layout.clusters) ? layout.clusters : [];
  const regions = source
    .map(readRegion)
    .filter((region): region is ClusterRegion => region !== null)
    .sort(
      (left, right) =>
        right.count - left.count || left.label.localeCompare(right.label),
    );
  return { regions, nodeClusters: readMap(layout.node_clusters) };
}

function nodePoint(node: ClusterNode): Point3 | null {
  if (![node.x, node.y, node.z].every((part) => Number.isFinite(part))) return null;
  return [node.x as number, node.y as number, node.z as number];
}

/** Recomputes counts and centroids from the nodes actually present in the view. */
export function viewRegions(
  set: ClusterSet,
  nodes: readonly ClusterNode[],
): ClusterRegion[] {
  const regions = new Map(set.regions.map((region) => [region.id, region]));
  const groups = new Map<string, { count: number; points: Point3[] }>();
  for (const node of nodes) {
    const regionId = set.nodeClusters[node.id];
    if (!regionId || !regions.has(regionId)) continue;
    const group = groups.get(regionId) ?? { count: 0, points: [] };
    group.count += 1;
    const point = nodePoint(node);
    if (point) group.points.push(point);
    groups.set(regionId, group);
  }

  return [...groups.entries()]
    .map(([id, group]) => {
      const region = regions.get(id) as ClusterRegion;
      if (group.points.length === 0) return { ...region, count: group.count };
      const sums = group.points.reduce(
        (total, point) => [
          total[0] + point[0],
          total[1] + point[1],
          total[2] + point[2],
        ],
        [0, 0, 0] as [number, number, number],
      );
      const size = group.points.length;
      const centroid: Point3 = [sums[0] / size, sums[1] / size, sums[2] / size];
      return { ...region, count: group.count, centroid };
    })
    .sort(
      (left, right) =>
        right.count - left.count || left.label.localeCompare(right.label),
    );
}

function labelBox(point: RegionPoint): RegionBox {
  const width = Math.min(224, Math.max(82, point.region.label.length * 7.2 + 30));
  return {
    left: point.x - width / 2,
    right: point.x + width / 2,
    top: point.y - 15,
    bottom: point.y + 15,
  };
}

function boxesTouch(left: RegionBox, right: RegionBox, gap = 14): boolean {
  return !(
    left.right + gap < right.left ||
    left.left - gap > right.right ||
    left.bottom + gap < right.top ||
    left.top - gap > right.bottom
  );
}

function labelCap(view: RegionView): number {
  const base = view.width < 560 ? 2 : view.width < 960 ? 4 : 6;
  if (view.scale >= 2.8) return 0;
  if (view.scale >= 2.2) return Math.min(1, base);
  if (view.scale >= 1.45) return Math.max(1, base - 2);
  return base;
}

function pointScore(point: RegionPoint, activeId?: string | null): number {
  const active = point.region.id === activeId ? 1_000_000 : 0;
  return active + Math.log2(point.region.count + 1) * 100 - point.depth * 12;
}

function inFrame(point: RegionPoint, view: RegionView): boolean {
  const pad = 32;
  const top = view.width < 480 ? 176 : view.width < 720 ? 132 : 88;
  const bottom = view.width < 720 ? 58 : 50;
  return (
    point.visible !== false &&
    point.depth >= -1 &&
    point.depth <= 1 &&
    point.x >= pad &&
    point.x <= view.width - pad &&
    point.y >= top &&
    point.y <= view.height - bottom
  );
}

function labelOpacity(point: RegionPoint, scale: number): number {
  const depthFade = Math.max(0, Math.min(0.2, (point.depth + 1) * 0.1));
  const zoomFade = Math.max(0, Math.min(0.16, (scale - 1) * 0.08));
  return Math.max(0.46, Math.min(0.9, 0.9 - depthFade - zoomFade));
}

/**
 * Selects a sparse set of projected labels. Scale is one at the fitted overview and
 * increases as the camera moves closer. At close range region labels disappear.
 */
export function pickRegions(
  points: readonly RegionPoint[],
  view: RegionView,
): VisibleRegion[] {
  const cap = Math.min(view.limit ?? Number.POSITIVE_INFINITY, labelCap(view));
  if (view.enabled === false || cap <= 0 || view.width <= 0 || view.height <= 0) {
    return [];
  }
  const blocked = [...(view.reserved ?? [])];
  const chosen: VisibleRegion[] = [];
  const ranked = points
    .filter((point) => inFrame(point, view))
    .sort(
      (left, right) =>
        pointScore(right, view.activeId) - pointScore(left, view.activeId) ||
        left.region.label.localeCompare(right.region.label),
    );

  for (const point of ranked) {
    const box = labelBox(point);
    if (blocked.some((other) => boxesTouch(box, other))) continue;
    chosen.push({ ...point, opacity: labelOpacity(point, view.scale) });
    blocked.push(box);
    if (chosen.length === cap) break;
  }
  return chosen;
}
