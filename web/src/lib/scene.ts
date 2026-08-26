import {
  BoxGeometry,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshPhongMaterial,
  OctahedronGeometry,
  SphereGeometry,
  type BufferGeometry,
  type Material,
} from "three";
import type { Theme } from "../hooks/theme";
import type { GraphNode, GraphNodeKind } from "../types";

const materials = new Map<string, Material>();
const shapes = new Map<string, BufferGeometry>();
const objects = new WeakMap<GraphNode, { key: string; group: Group }>();

function nodeShape(kind: GraphNodeKind, detail: number): BufferGeometry {
  const key = `${kind}:${detail}`;
  const cached = shapes.get(key);
  if (cached) return cached;
  const shape =
    kind === "topic"
      ? new SphereGeometry(1, detail, Math.max(6, Math.round(detail * 0.75)))
      : kind === "paper"
        ? new SphereGeometry(1, detail, Math.max(5, Math.round(detail * 0.7)))
        : kind === "trick"
          ? new OctahedronGeometry(1, 0)
          : new BoxGeometry(1.55, 1.55, 1.55);
  shapes.set(key, shape);
  return shape;
}

function nodeSize(node: GraphNode, simple = false): number {
  const base = 1.15 + Math.sqrt(node.val) * 0.72;
  if (node.kind === "paper") return base * 0.72;
  return simple ? base * 1.9 : base;
}

function nodeMat(node: GraphNode, emphasized: boolean, simple = false): Material {
  const key = `${node.kind}:${node.color}:${emphasized}:${simple}`;
  const cached = materials.get(key);
  if (cached) return cached;

  const material = new MeshPhongMaterial({
    color: node.color,
    emissive: emphasized ? node.color : "#000000",
    emissiveIntensity: emphasized ? 0.42 : 0,
    flatShading: node.kind === "trick" || node.kind === "idea",
    shininess: emphasized ? 88 : 38,
    transparent: true,
    opacity: emphasized ? 1 : 0.9,
  });
  materials.set(key, material);
  return material;
}

function haloMat(theme: Theme): Material {
  const key = `halo:${theme}`;
  const cached = materials.get(key);
  if (cached) return cached;

  const material = new MeshBasicMaterial({
    color: theme === "dark" ? "#f4f0e7" : "#332b25",
    transparent: true,
    opacity: 0.82,
    wireframe: true,
  });
  materials.set(key, material);
  return material;
}

export function buildNode(
  node: GraphNode,
  theme: Theme,
  detail = 10,
  simple = false,
): Group {
  const key = `${theme}:${detail}:${simple}`;
  const cached = objects.get(node);
  if (cached?.key === key && cached.group.getObjectByName("shape")) {
    return cached.group;
  }
  const size = nodeSize(node, simple);
  const group = new Group();
  const geometry = nodeShape(node.kind, detail);
  const shape = new Mesh(geometry, nodeMat(node, false, simple));
  shape.name = "shape";
  shape.scale.setScalar(size);
  group.add(shape);
  if (!simple) {
    const halo = new Mesh(geometry, haloMat(theme));
    halo.name = "halo";
    halo.scale.setScalar(size * 1.34);
    halo.visible = false;
    group.add(halo);
  }

  objects.set(node, { key, group });
  return group;
}

export function markNode(
  node: GraphNode,
  emphasized: boolean,
  theme: Theme,
  detail = 10,
  simple = false,
): void {
  const group = buildNode(node, theme, detail, simple);
  const shape = group.getObjectByName("shape") as Mesh;
  let halo = group.getObjectByName("halo") as Mesh | undefined;
  if (emphasized && !halo) {
    halo = new Mesh(shape.geometry, haloMat(theme));
    halo.name = "halo";
    halo.scale.setScalar(nodeSize(node, simple) * 1.34);
    group.add(halo);
  }
  shape.material = nodeMat(node, emphasized, simple);
  if (!halo) return;
  halo.visible = emphasized;
}
