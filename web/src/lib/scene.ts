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
import SpriteText from "three-spritetext";
import type { Theme } from "../hooks/theme";
import type { GraphNode, GraphNodeKind } from "../types";

const materials = new Map<string, Material>();
const shapes = new Map<string, BufferGeometry>();
const objects = new WeakMap<GraphNode, { key: string; group: Group }>();
export const LABEL_FONT = "Libre Baskerville Variable";

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

function nodeSize(node: GraphNode): number {
  const base = 1.15 + Math.sqrt(node.val) * 0.72;
  return node.kind === "paper" ? base * 0.72 : base;
}

function nodeMat(node: GraphNode, emphasized: boolean, simple = false): Material {
  const key = `${node.kind}:${node.color}:${emphasized}:${simple}`;
  const cached = materials.get(key);
  if (cached) return cached;

  const MaterialType = simple && !emphasized ? MeshBasicMaterial : MeshPhongMaterial;
  const material = new MaterialType({
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

function nodeLabel(
  node: GraphNode,
  size: number,
  theme: Theme,
  maxChars: number,
): SpriteText {
  const text =
    node.label.length > maxChars
      ? `${node.label.slice(0, Math.max(1, maxChars - 2))}…`
      : node.label;
  const label = new SpriteText(text, 5.4);
  label.fontFace = LABEL_FONT;
  label.fontWeight = "600";
  label.color = theme === "dark" ? "#f4f0e7" : "#2d2722";
  label.backgroundColor =
    theme === "dark" ? "rgba(17,24,19,.88)" : "rgba(250,246,238,.9)";
  label.borderColor = theme === "dark" ? "rgba(244,240,231,.24)" : "rgba(45,39,34,.2)";
  label.borderWidth = 0.35;
  label.borderRadius = 3;
  label.padding = [2.4, 1.4];
  label.position.y = size + 4.4;
  label.material.depthTest = false;
  label.material.depthWrite = false;
  label.renderOrder = 1_000;
  return label;
}

export function buildNode(
  node: GraphNode,
  theme: Theme,
  detail = 10,
  maxChars = 42,
  simple = false,
): Group {
  const key = `${theme}:${detail}:${maxChars}:${simple}`;
  const cached = objects.get(node);
  if (cached?.key === key && cached.group.getObjectByName("shape")) {
    return cached.group;
  }
  if (cached) dropLabel(cached.group);

  const size = nodeSize(node);
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

function dropLabel(group: Group): void {
  const label = group.getObjectByName("label") as SpriteText | undefined;
  if (!label) return;
  label.material.map?.dispose();
  label.material.dispose();
  label.geometry.dispose();
  group.remove(label);
}

export function markNode(
  node: GraphNode,
  emphasized: boolean,
  theme: Theme,
  detail = 10,
  maxChars = 42,
  simple = false,
): void {
  const group = buildNode(node, theme, detail, maxChars, simple);
  const shape = group.getObjectByName("shape") as Mesh;
  let halo = group.getObjectByName("halo") as Mesh | undefined;
  if (emphasized && !halo) {
    halo = new Mesh(shape.geometry, haloMat(theme));
    halo.name = "halo";
    halo.scale.setScalar(nodeSize(node) * 1.34);
    group.add(halo);
  }
  shape.material = nodeMat(node, emphasized, simple);
  if (!halo) return;
  halo.visible = emphasized;

  if (!emphasized) {
    dropLabel(group);
  } else if (!group.getObjectByName("label")) {
    const label = nodeLabel(node, nodeSize(node), theme, maxChars);
    label.name = "label";
    group.add(label);
  }
}
