import {
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  Points,
  ShaderMaterial,
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

export type CloudSwarm = Points<BufferGeometry, ShaderMaterial>;

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
  const base = new Color(theme === "dark" ? "#83b5bf" : "#4f7f89");
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

export function buildCloud(data: CloudData, theme: Theme): CloudSwarm {
  const count = data.scopes.length;
  const palette = [
    new Color(theme === "dark" ? "#8fc6cf" : "#3f7884"),
    new Color(theme === "dark" ? "#d8ba78" : "#967129"),
    new Color(theme === "dark" ? "#64736d" : "#9b968c"),
  ];
  const alpha = [0.96, 0.78, 0.28];
  const sizes = [1.35, 1.12, 0.62];
  const colors = new Float32Array(count * 3);
  const opacity = new Float32Array(count);
  const scales = new Float32Array(count);
  for (let index = 0; index < count; index += 1) {
    const scope = data.scopes[index];
    const color = palette[scope];
    colors.set([color.r, color.g, color.b], index * 3);
    opacity[index] = alpha[scope];
    scales[index] = sizes[scope];
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(data.positions, 3));
  geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
  geometry.setAttribute("scale", new Float32BufferAttribute(scales, 1));
  geometry.setAttribute("opacity", new Float32BufferAttribute(opacity, 1));
  geometry.computeBoundingSphere();
  const size = count >= 1_000_000 ? 2.4 : count >= 250_000 ? 3.2 : 4.8;
  const points = new Points(geometry, swarmMaterial(size));
  points.name = "archive-cloud";
  points.renderOrder = 1;
  return points;
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
