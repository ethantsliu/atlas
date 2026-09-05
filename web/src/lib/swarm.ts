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
import { CLOUD_VERTEX } from "./cloudshader";
import {
  CLOUD_LOD_MAX,
  CLOUD_REST_MS,
  cloudOpacity,
  cloudReduced,
  cloudSettle,
  cloudSize,
  cloudTone,
  lodIds,
  motionTone,
  type CloudDetail,
} from "./cloudview";

export {
  CLOUD_LARGE_SETTLE_MS,
  CLOUD_LOD_CAP,
  CLOUD_LOD_MAX,
  CLOUD_REST_MS,
  CLOUD_SETTLE_MS,
  CLOUD_STABLE_LIMIT,
  cloudDrawCount,
  cloudLod,
  cloudOpacity,
  cloudReduced,
  cloudSettle,
  cloudSize,
  cloudTone,
  lodIds,
  motionTone,
  type CloudDetail,
  type CloudTone,
} from "./cloudview";

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
  detail: CloudDetail;
  dropped: boolean;
  frame: number;
  full: BufferAttribute;
  gl: WebGL2RenderingContext | null;
  held: boolean;
  loaded: number;
  moving: boolean;
  rest: ReturnType<typeof setTimeout> | null;
  settling: boolean;
  view: Float64Array | null;
};

type CloudControl = {
  addEventListener?: (type: string, listener: () => void) => void;
  removeEventListener?: (type: string, listener: () => void) => void;
};

export type CloudSwarm = Points<BufferGeometry, ShaderMaterial> & {
  userData: CloudStore;
};

export const CLOUD_BATCH = 65_536;
export const CLOUD_VIEW_EPS = 1e-6;

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
  const reduced = cloudReduced(store.data.positions.length / 3, store.detail, coarse);
  const position = reduced ? store.coarse : store.full;
  if (points.geometry.getAttribute("position") !== position) {
    points.geometry.setAttribute("position", position);
  }
  points.geometry.setDrawRange(0, reduced ? store.coarseLoaded : store.loaded);
  setTone(points, reduced);
}

function clearRest(store: CloudStore): void {
  if (store.rest) clearTimeout(store.rest);
  store.rest = null;
}

function armRest(points: CloudSwarm): void {
  const store = points.userData;
  clearRest(store);
  if (store.held) return;
  const delay = store.settling
    ? cloudSettle(store.data.positions.length / 3, store.detail)
    : CLOUD_REST_MS;
  store.rest = setTimeout(() => restCloud(points), delay);
}

export function holdCloud(points: CloudSwarm): void {
  const store = points.userData;
  store.held = true;
  store.settling = false;
  clearRest(store);
  if (store.moving) showCloud(points, true);
}

export function releaseCloud(points: CloudSwarm): void {
  const store = points.userData;
  store.held = false;
  store.settling = true;
  if (!store.moving) return;
  armRest(points);
}

export function bindCloud(
  points: CloudSwarm,
  control: CloudControl | null | undefined,
  target?: EventTarget | null,
  releaseTarget: EventTarget | null | undefined = target,
): () => void {
  const pointers = new Set<number>();
  const hold = () => holdCloud(points);
  const release = () => {
    if (pointers.size === 0) releaseCloud(points);
  };
  const press = (event: Event) => {
    pointers.add((event as PointerEvent).pointerId);
    holdCloud(points);
  };
  const lift = (event: Event) => {
    pointers.delete((event as PointerEvent).pointerId);
    release();
  };
  control?.addEventListener?.("start", hold);
  control?.addEventListener?.("end", release);
  target?.addEventListener("pointerdown", press);
  releaseTarget?.addEventListener("pointerup", lift, true);
  releaseTarget?.addEventListener("pointercancel", lift, true);
  return () => {
    control?.removeEventListener?.("start", hold);
    control?.removeEventListener?.("end", release);
    target?.removeEventListener("pointerdown", press);
    releaseTarget?.removeEventListener("pointerup", lift, true);
    releaseTarget?.removeEventListener("pointercancel", lift, true);
  };
}

export function moveCloud(points: CloudSwarm, after?: () => void): void {
  const store = points.userData;
  store.moving = true;
  const count = store.data.positions.length / 3;
  const changes =
    cloudReduced(count, store.detail, true) !==
    cloudReduced(count, store.detail, false);
  if (after && changes) store.after = after;
  else if (!changes) store.after = null;
  showCloud(points, true);
  armRest(points);
}

export function restCloud(points: CloudSwarm): void {
  const store = points.userData;
  clearRest(store);
  if (store.held) return;
  const after = store.after;
  store.after = null;
  store.moving = false;
  store.settling = false;
  showCloud(points, false);
  after?.();
}

function viewMoved(store: CloudStore, camera: Camera): boolean {
  const world = camera.matrixWorld.elements;
  const projection = camera.projectionMatrix.elements;
  if (!store.view) {
    store.view = new Float64Array([...world, ...projection]);
    return false;
  }
  const values = store.view;
  let drift = 0;
  for (let index = 0; index < world.length; index += 1) {
    const delta = values[index] - world[index];
    drift += delta * delta;
  }
  for (let index = 0; index < projection.length; index += 1) {
    const target = world.length + index;
    const delta = values[target] - projection[index];
    drift += delta * delta;
  }
  values.set(world);
  values.set(projection, world.length);
  return drift > CLOUD_VIEW_EPS;
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
  radius: number,
): ShaderMaterial {
  const colors = paperColors(theme);
  return new ShaderMaterial({
    vertexShader: CLOUD_VERTEX,
    fragmentShader: FRAGMENT,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    uniforms: {
      cloudRadius: { value: Math.max(radius, Number.EPSILON) },
      pointSize: { value: pointSize },
      paperColor: { value: colors.base },
      paperAccent: { value: colors.accent },
      paperWarm: { value: colors.warm },
      pointOpacity: { value: pointOpacity },
    },
  });
}

function paperColor(theme: Theme): Color {
  return new Color(theme === "dark" ? "#83b5bf" : "#4f7f89");
}

function paperColors(theme: Theme): Record<"base" | "accent" | "warm", Color> {
  return {
    base: paperColor(theme),
    accent: new Color(theme === "dark" ? "#91a8e8" : "#526fa2"),
    warm: new Color(theme === "dark" ? "#dfa6bb" : "#a96578"),
  };
}

function setTone(points: CloudSwarm, moving: boolean): void {
  const tone = moving
    ? motionTone(points.userData.data.scopes.length)
    : cloudTone(points.userData.data.scopes.length);
  points.material.uniforms.pointOpacity.value = tone.opacity;
  points.material.uniforms.pointSize.value = tone.size;
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
  // Foreground papers and archive papers share one resting screen-space size.
  // Selection/hover can still enlarge the foreground point intentionally.
  const material = swarmMaterial(1.2);
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
  detail: CloudDetail = "sample",
): CloudSwarm {
  const count = data.scopes.length;
  const geometry = new BufferGeometry();
  // Full-only rendering never reads the motion sample. Avoid retaining its
  // CPU array, index map, and GPU buffer beside the exact 3.15M-point store.
  const coarseIds = detail === "full" ? new Uint32Array(0) : lodIds(count);
  const coarseData = new Float32Array(coarseIds.length * 3);
  let gl: WebGL2RenderingContext | null = null;
  let buffer: WebGLBuffer | null = null;
  let coarseBuffer: WebGLBuffer | null = null;
  let full: BufferAttribute;
  let coarse: BufferAttribute;
  if (renderer) {
    gl = renderer.getContext() as WebGL2RenderingContext;
    buffer = gl.createBuffer();
    coarseBuffer = coarseIds.length > 0 ? gl.createBuffer() : null;
    if (!buffer || (coarseIds.length > 0 && !coarseBuffer)) {
      if (buffer) gl.deleteBuffer(buffer);
      if (coarseBuffer) gl.deleteBuffer(coarseBuffer);
      throw new Error("Paper cloud GPU allocation failed");
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data.positions.byteLength, gl.DYNAMIC_DRAW);
    if (coarseBuffer) {
      gl.bindBuffer(gl.ARRAY_BUFFER, coarseBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, coarseData.byteLength, gl.DYNAMIC_DRAW);
    }
    full = new GLBufferAttribute(
      buffer,
      gl.FLOAT,
      3,
      4,
      count,
    ) as unknown as BufferAttribute;
    coarse = coarseBuffer
      ? (new GLBufferAttribute(
          coarseBuffer,
          gl.FLOAT,
          3,
          4,
          coarseIds.length,
        ) as unknown as BufferAttribute)
      : full;
    geometry.setAttribute("position", full);
    geometry.setDrawRange(0, 0);
  } else {
    full = new BufferAttribute(data.positions, 3);
    full.setUsage(DynamicDrawUsage);
    coarse = coarseIds.length > 0 ? new BufferAttribute(coarseData, 3) : full;
    if (coarse !== full) coarse.setUsage(DynamicDrawUsage);
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
    cloudMaterial(size, opacity, theme, data.radius),
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
    detail,
    dropped: false,
    frame: 0,
    full,
    gl,
    held: false,
    loaded: renderer ? 0 : data.loaded,
    moving: false,
    rest: null,
    settling: false,
    view: null,
  };
  if (!renderer && data.loaded > 0) {
    fillLod(points.userData, 0, data.loaded);
    showCloud(points, false);
  }
  points.onBeforeRender = (_renderer, _scene, camera) => {
    if (viewMoved(points.userData, camera)) moveCloud(points, redraw);
  };
  return points;
}

export function setCloudDetail(points: CloudSwarm, detail: CloudDetail): boolean {
  if (points.userData.detail === detail) return false;
  if (detail === "sample" && points.userData.coarseIds.length === 0) return false;
  points.userData.detail = detail;
  showCloud(points, points.userData.moving);
  return true;
}

export function growCloud(points: CloudSwarm, data: CloudData): void {
  const store = points.userData;
  if (store.dropped) return;
  store.data = data;
  points.geometry.boundingSphere!.radius = Math.max(data.radius, Number.EPSILON);
  points.material.uniforms.cloudRadius.value = Math.max(data.radius, Number.EPSILON);
  if (store.frame || store.loaded >= data.loaded) return;
  store.frame = requestAnimationFrame(() => {
    store.frame = 0;
    if (store.dropped) return;
    const start = store.loaded;
    const total = store.data.positions.length / 3;
    const complete = total > CLOUD_LOD_MAX && store.data.loaded === total;
    const end =
      store.bulk || complete
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
