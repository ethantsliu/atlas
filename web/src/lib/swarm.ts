import {
  BufferAttribute,
  BufferGeometry,
  Color,
  DynamicDrawUsage,
  Float32BufferAttribute,
  GLBufferAttribute,
  Points,
  ShaderMaterial,
  Sphere,
  Vector3,
  type Camera,
  type WebGLRenderer,
} from "three";
import type { Theme } from "../hooks/theme";
import type { GraphNode } from "../types";
import type { CloudData } from "./cloud";

const VERTEX = `
  attribute float scale;
  attribute float opacity;
  varying vec3 pointColor;
  varying float pointAlpha;
  uniform float pointSize;
  void main() {
    pointColor = color;
    pointAlpha = opacity;
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * view;
    gl_PointSize = pointSize * scale;
  }
`;

const CLOUD_VERTEX = `
  varying vec3 pointColor;
  varying float pointAlpha;
  uniform vec3 paperColor;
  uniform float pointOpacity;
  uniform float pointSize;
  void main() {
    pointColor = paperColor;
    pointAlpha = pointOpacity;
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * view;
    gl_PointSize = pointSize;
  }
`;

const FRAGMENT = `
  varying vec3 pointColor;
  varying float pointAlpha;
  void main() {
    vec2 center = gl_PointCoord - vec2(0.5);
    float radius = length(center);
    float alpha = 1.0 - smoothstep(0.38, 0.5, radius);
    if (alpha < 0.02) discard;
    gl_FragColor = vec4(pointColor, alpha * pointAlpha);
  }
`;

type SwarmData = {
  nodes: GraphNode[];
  indexes: Map<string, number>;
  active: Set<number>;
  base: Color;
  hot: Color;
};

export type PaperSwarm = Points<BufferGeometry, ShaderMaterial> & {
  userData: SwarmData;
};

type CloudStore = {
  after: (() => void) | null;
  buffer: WebGLBuffer | null;
  bulk: boolean;
  coarse: BufferAttribute;
  coarseBuffer: WebGLBuffer | null;
  coarseData: Float32Array;
  coarseIds: Uint32Array;
  coarseLoaded: number;
  data: CloudData;
  dropped: boolean;
  frame: number;
  full: BufferAttribute;
  gl: WebGL2RenderingContext | null;
  loaded: number;
  moving: boolean;
  rest: ReturnType<typeof setTimeout> | null;
  view: Float64Array | null;
};

export type CloudSwarm = Points<BufferGeometry, ShaderMaterial> & {
  userData: CloudStore;
};

export const CLOUD_BATCH = 65_536;
export const CLOUD_LOD_MAX = 100_000;
export const CLOUD_REST_MS = 160;

export function cloudLod(count: number): number {
  if (count <= CLOUD_LOD_MAX) return Math.max(0, count);
  const floor = count >= 3_000_000 ? CLOUD_LOD_MAX : 72_000;
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

function lowerId(ids: Uint32Array, target: number): number {
  let low = 0;
  let high = ids.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (ids[middle] < target) low = middle + 1;
    else high = middle;
  }
  return low;
}

function fillLod(store: CloudStore, start: number, end: number): [number, number] {
  const first = lowerId(store.coarseIds, start);
  const last = lowerId(store.coarseIds, end);
  for (let index = first; index < last; index += 1) {
    const source = store.coarseIds[index] * 3;
    const target = index * 3;
    store.coarseData[target] = store.data.positions[source];
    store.coarseData[target + 1] = store.data.positions[source + 1];
    store.coarseData[target + 2] = store.data.positions[source + 2];
  }
  store.coarseLoaded = last;
  return [first, last];
}

function showCloud(points: CloudSwarm, coarse: boolean): void {
  const store = points.userData;
  const position = coarse ? store.coarse : store.full;
  if (points.geometry.getAttribute("position") !== position) {
    points.geometry.setAttribute("position", position);
  }
  points.geometry.setDrawRange(0, coarse ? store.coarseLoaded : store.loaded);
}

export function moveCloud(points: CloudSwarm, after?: () => void): void {
  const store = points.userData;
  store.moving = true;
  if (after) store.after = after;
  showCloud(points, true);
  if (store.rest) clearTimeout(store.rest);
  store.rest = setTimeout(() => restCloud(points), CLOUD_REST_MS);
}

export function restCloud(points: CloudSwarm): void {
  const store = points.userData;
  const after = store.after;
  if (store.rest) clearTimeout(store.rest);
  store.after = null;
  store.rest = null;
  store.moving = false;
  showCloud(points, false);
  after?.();
}

function viewMoved(store: CloudStore, camera: Camera): boolean {
  const world = camera.matrixWorld.elements;
  const projection = camera.projectionMatrix.elements;
  const values = store.view ?? new Float64Array(world.length + projection.length);
  let changed = false;
  for (let index = 0; index < world.length; index += 1) {
    if (values[index] !== world[index]) changed = store.view !== null;
    values[index] = world[index];
  }
  for (let index = 0; index < projection.length; index += 1) {
    const target = world.length + index;
    if (values[target] !== projection[index]) changed = store.view !== null;
    values[target] = projection[index];
  }
  store.view = values;
  return changed;
}

function swarmMaterial(pointSize: number): ShaderMaterial {
  return new ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    vertexColors: true,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    uniforms: { pointSize: { value: pointSize } },
  });
}

function cloudMaterial(
  pointSize: number,
  pointOpacity: number,
  theme: Theme,
): ShaderMaterial {
  return new ShaderMaterial({
    vertexShader: CLOUD_VERTEX,
    fragmentShader: FRAGMENT,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    uniforms: {
      pointSize: { value: pointSize },
      paperColor: { value: paperColor(theme) },
      pointOpacity: { value: pointOpacity },
    },
  });
}

function paperColor(theme: Theme): Color {
  return new Color(theme === "dark" ? "#83b5bf" : "#4f7f89");
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

export function swarmNodes(nodes: GraphNode[]): GraphNode[] {
  return nodes.filter(
    (node) =>
      node.kind === "paper" &&
      Number.isFinite(node.sx ?? node.x) &&
      Number.isFinite(node.sy ?? node.y) &&
      Number.isFinite(node.sz ?? node.z),
  );
}

export function buildSwarm(nodes: GraphNode[], theme: Theme): PaperSwarm {
  const papers = swarmNodes(nodes);
  const base = paperColor(theme);
  const hot = new Color(theme === "dark" ? "#f0c4ae" : "#a94730");
  const positions: number[] = [];
  const colors: number[] = [];
  for (const node of papers) {
    positions.push(
      node.sx ?? node.x ?? 0,
      node.sy ?? node.y ?? 0,
      node.sz ?? node.z ?? 0,
    );
    colors.push(base.r, base.g, base.b);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
  geometry.setAttribute(
    "scale",
    new Float32BufferAttribute(new Float32Array(papers.length).fill(1), 1),
  );
  geometry.setAttribute(
    "opacity",
    new Float32BufferAttribute(new Float32Array(papers.length).fill(0.96), 1),
  );
  geometry.computeBoundingSphere();
  const material = swarmMaterial(5.8);
  const points = new Points(geometry, material) as PaperSwarm;
  points.name = "paper-swarm";
  points.renderOrder = 2;
  points.userData = {
    nodes: papers,
    indexes: new Map(papers.map((node, index) => [node.id, index])),
    active: new Set(),
    base,
    hot,
  };
  return points;
}

export function buildCloud(
  data: CloudData,
  theme: Theme,
  renderer?: WebGLRenderer,
  redraw?: () => void,
): CloudSwarm {
  const count = data.scopes.length;
  const geometry = new BufferGeometry();
  const coarseIds = lodIds(count);
  const coarseData = new Float32Array(coarseIds.length * 3);
  let gl: WebGL2RenderingContext | null = null;
  let buffer: WebGLBuffer | null = null;
  let coarseBuffer: WebGLBuffer | null = null;
  let full: BufferAttribute;
  let coarse: BufferAttribute;
  if (renderer) {
    gl = renderer.getContext() as WebGL2RenderingContext;
    buffer = gl.createBuffer();
    coarseBuffer = gl.createBuffer();
    if (!buffer || !coarseBuffer) {
      if (buffer) gl.deleteBuffer(buffer);
      if (coarseBuffer) gl.deleteBuffer(coarseBuffer);
      throw new Error("Paper cloud GPU allocation failed");
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data.positions.byteLength, gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, coarseBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, coarseData.byteLength, gl.DYNAMIC_DRAW);
    full = new GLBufferAttribute(
      buffer,
      gl.FLOAT,
      3,
      4,
      count,
    ) as unknown as BufferAttribute;
    coarse = new GLBufferAttribute(
      coarseBuffer,
      gl.FLOAT,
      3,
      4,
      coarseIds.length,
    ) as unknown as BufferAttribute;
    geometry.setAttribute("position", full);
    geometry.setDrawRange(0, 0);
  } else {
    full = new BufferAttribute(data.positions, 3);
    full.setUsage(DynamicDrawUsage);
    coarse = new BufferAttribute(coarseData, 3);
    coarse.setUsage(DynamicDrawUsage);
    geometry.setAttribute("position", full);
    geometry.setDrawRange(0, data.loaded);
  }
  geometry.boundingSphere = new Sphere(
    new Vector3(),
    Math.max(data.radius, Number.EPSILON),
  );
  const size = cloudSize(count);
  const opacity = cloudOpacity(count);
  const points = new Points(
    geometry,
    cloudMaterial(size, opacity, theme),
  ) as CloudSwarm;
  points.name = "archive-cloud";
  points.renderOrder = 1;
  points.frustumCulled = false;
  points.userData = {
    after: null,
    buffer,
    bulk: Boolean(renderer && data.loaded === count),
    coarse,
    coarseBuffer,
    coarseData,
    coarseIds,
    coarseLoaded: 0,
    data,
    dropped: false,
    frame: 0,
    full,
    gl,
    loaded: renderer ? 0 : data.loaded,
    moving: false,
    rest: null,
    view: null,
  };
  if (!renderer && data.loaded > 0) fillLod(points.userData, 0, data.loaded);
  points.onBeforeRender = (_renderer, _scene, camera) => {
    if (viewMoved(points.userData, camera)) moveCloud(points, redraw);
  };
  return points;
}

export function growCloud(points: CloudSwarm, data: CloudData): void {
  const store = points.userData;
  if (store.dropped) return;
  store.data = data;
  points.geometry.boundingSphere!.radius = Math.max(data.radius, Number.EPSILON);
  if (store.frame || store.loaded >= data.loaded) return;
  store.frame = requestAnimationFrame(() => {
    store.frame = 0;
    if (store.dropped) return;
    const start = store.loaded;
    const end = store.bulk
      ? store.data.loaded
      : Math.min(store.data.loaded, start + CLOUD_BATCH);
    if (end <= start) return;
    const [coarseStart, coarseEnd] = fillLod(store, start, end);
    if (store.gl && store.buffer) {
      store.gl.bindBuffer(store.gl.ARRAY_BUFFER, store.buffer);
      store.gl.bufferSubData(
        store.gl.ARRAY_BUFFER,
        start * 3 * Float32Array.BYTES_PER_ELEMENT,
        store.data.positions.subarray(start * 3, end * 3),
      );
      if (store.coarseBuffer && coarseEnd > coarseStart) {
        store.gl.bindBuffer(store.gl.ARRAY_BUFFER, store.coarseBuffer);
        store.gl.bufferSubData(
          store.gl.ARRAY_BUFFER,
          coarseStart * 3 * Float32Array.BYTES_PER_ELEMENT,
          store.coarseData.subarray(coarseStart * 3, coarseEnd * 3),
        );
      }
    } else {
      store.full.addUpdateRange(start * 3, (end - start) * 3);
      store.full.needsUpdate = true;
      if (coarseEnd > coarseStart) {
        store.coarse.addUpdateRange(coarseStart * 3, (coarseEnd - coarseStart) * 3);
        store.coarse.needsUpdate = true;
      }
    }
    store.bulk = false;
    store.loaded = end;
    showCloud(points, store.moving);
    if (end < store.data.loaded) growCloud(points, store.data);
  });
}

export function paintCloud(points: CloudSwarm, theme: Theme): void {
  points.material.uniforms.paperColor.value.copy(paperColor(theme));
}

export function dropCloud(points: CloudSwarm): void {
  points.userData.dropped = true;
  if (points.userData.frame) cancelAnimationFrame(points.userData.frame);
  points.userData.frame = 0;
  if (points.userData.rest) clearTimeout(points.userData.rest);
  points.userData.after = null;
  points.userData.rest = null;
  if (points.userData.gl && points.userData.buffer) {
    points.userData.gl.deleteBuffer(points.userData.buffer);
    points.userData.buffer = null;
  }
  if (points.userData.gl && points.userData.coarseBuffer) {
    points.userData.gl.deleteBuffer(points.userData.coarseBuffer);
    points.userData.coarseBuffer = null;
  }
}

export function markSwarm(
  swarm: PaperSwarm,
  selected: string | null,
  hovered: string | null,
): void {
  const data = swarm.userData;
  const next = new Set(
    [selected, hovered]
      .map((id) => (id ? data.indexes.get(id) : undefined))
      .filter((index): index is number => index !== undefined),
  );
  const changed = new Set([...data.active, ...next]);
  const colors = swarm.geometry.getAttribute("color");
  const scales = swarm.geometry.getAttribute("scale");
  for (const index of changed) {
    const active = next.has(index);
    const color = active ? data.hot : data.base;
    colors.setXYZ(index, color.r, color.g, color.b);
    scales.setX(index, active ? (data.nodes[index].id === selected ? 2 : 1.55) : 1);
  }
  colors.needsUpdate = true;
  scales.needsUpdate = true;
  data.active = next;
}

export function swarmNode(
  swarm: PaperSwarm,
  index: number | undefined,
): GraphNode | null {
  return index == null ? null : (swarm.userData.nodes[index] ?? null);
}
