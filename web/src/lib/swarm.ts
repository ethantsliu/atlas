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
  buffer: WebGLBuffer | null;
  data: CloudData;
  frame: number;
  gl: WebGL2RenderingContext | null;
};

export type CloudSwarm = Points<BufferGeometry, ShaderMaterial> & {
  userData: CloudStore;
};

export const CLOUD_BATCH = 65_536;

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
): CloudSwarm {
  const count = data.scopes.length;
  const geometry = new BufferGeometry();
  let gl: WebGL2RenderingContext | null = null;
  let buffer: WebGLBuffer | null = null;
  if (renderer) {
    gl = renderer.getContext() as WebGL2RenderingContext;
    buffer = gl.createBuffer();
    if (!buffer) throw new Error("Paper cloud GPU allocation failed");
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data.positions.byteLength, gl.DYNAMIC_DRAW);
    geometry.setAttribute(
      "position",
      new GLBufferAttribute(
        buffer,
        gl.FLOAT,
        3,
        4,
        count,
      ) as unknown as BufferAttribute,
    );
    geometry.setDrawRange(0, 0);
  } else {
    const positions = new BufferAttribute(data.positions, 3);
    positions.setUsage(DynamicDrawUsage);
    geometry.setAttribute("position", positions);
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
  points.userData = { buffer, data, frame: 0, gl };
  return points;
}

export function growCloud(points: CloudSwarm, data: CloudData): void {
  const store = points.userData;
  store.data = data;
  points.geometry.boundingSphere!.radius = Math.max(data.radius, Number.EPSILON);
  if (store.frame || points.geometry.drawRange.count >= data.loaded) return;
  store.frame = requestAnimationFrame(() => {
    store.frame = 0;
    const start = points.geometry.drawRange.count;
    const end = Math.min(data.loaded, start + CLOUD_BATCH);
    if (end <= start) return;
    if (store.gl && store.buffer) {
      store.gl.bindBuffer(store.gl.ARRAY_BUFFER, store.buffer);
      store.gl.bufferSubData(
        store.gl.ARRAY_BUFFER,
        start * 3 * Float32Array.BYTES_PER_ELEMENT,
        data.positions.subarray(start * 3, end * 3),
      );
    } else {
      const positions = points.geometry.getAttribute("position") as BufferAttribute;
      positions.addUpdateRange(start * 3, (end - start) * 3);
      positions.needsUpdate = true;
    }
    points.geometry.setDrawRange(0, end);
    if (end < store.data.loaded) growCloud(points, store.data);
  });
}

export function paintCloud(points: CloudSwarm, theme: Theme): void {
  points.material.uniforms.paperColor.value.copy(paperColor(theme));
}

export function dropCloud(points: CloudSwarm): void {
  if (points.userData.frame) cancelAnimationFrame(points.userData.frame);
  points.userData.frame = 0;
  if (points.userData.gl && points.userData.buffer) {
    points.userData.gl.deleteBuffer(points.userData.buffer);
    points.userData.buffer = null;
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
