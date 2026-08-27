import type { ForceGraphMethods as Graph2d } from "react-force-graph-2d";
import type { GraphLink, GraphNode } from "../types";

export type CameraPoint = readonly [number, number, number];

export type CameraView = {
  target: CameraPoint;
  radius: number;
  yaw: number;
  pitch: number;
};

const CAMERA_RE =
  /^1_(-?\d+(?:\.\d)?)_(-?\d+(?:\.\d)?)_(-?\d+(?:\.\d)?)_(\d+(?:\.\d)?)_(-?\d+)_(-?\d+)$/;

function finiteRange(value: number, low: number, high: number): boolean {
  return Number.isFinite(value) && value >= low && value <= high;
}

function cleanZero(value: number): number {
  return Object.is(value, -0) ? 0 : value;
}

export function parseCamera(value: string | null): CameraView | null {
  if (!value || value.length > 64 || !/^[\x20-\x7e]+$/.test(value)) return null;
  const match = CAMERA_RE.exec(value);
  if (!match) return null;
  const [x, y, z, radius, yaw, pitch] = match.slice(1).map(Number);
  if (
    ![x, y, z].every((item) => finiteRange(item, -4096, 4096)) ||
    !finiteRange(radius, 8, 4096) ||
    !finiteRange(yaw, -180, 180) ||
    !finiteRange(pitch, -85, 85)
  ) {
    return null;
  }
  return {
    target: [cleanZero(x), cleanZero(y), cleanZero(z)],
    radius: cleanZero(radius),
    yaw: cleanZero(yaw),
    pitch: cleanZero(pitch),
  };
}

function roundOne(value: number): number {
  return cleanZero(Math.round(value * 10) / 10);
}

function oneDecimal(value: number): string {
  const clean = roundOne(value);
  return Number.isInteger(clean) ? String(clean) : clean.toFixed(1);
}

export function formatCamera(view: CameraView | null): string | null {
  if (!view) return null;
  const [x, y, z] = view.target.map(roundOne);
  const radius = roundOne(view.radius);
  const yaw = Math.round(view.yaw);
  const pitch = Math.round(view.pitch);
  if (
    ![x, y, z].every((item) => finiteRange(item, -4096, 4096)) ||
    !finiteRange(radius, 8, 4096) ||
    !finiteRange(yaw, -180, 180) ||
    !finiteRange(pitch, -85, 85)
  ) {
    return null;
  }
  const value = `1_${oneDecimal(x)}_${oneDecimal(y)}_${oneDecimal(z)}_${oneDecimal(radius)}_${yaw}_${pitch}`;
  return parseCamera(value) ? value : null;
}

type Point = { x: number; y: number; z: number };
type Controls = { target?: Point };
type Camera = { position: Point; fov?: number };

export type Camera3d = {
  camera: () => unknown;
  controls: () => object;
  cameraPosition: (
    position: Partial<Point>,
    lookAt?: Point,
    transitionMs?: number,
  ) => unknown;
};

export function read3d(graph: Camera3d | undefined): CameraView | null {
  if (!graph) return null;
  const camera = graph.camera() as Camera;
  const target = (graph.controls() as Controls).target;
  if (!target || !camera.fov) return null;
  const dx = camera.position.x - target.x;
  const dy = camera.position.y - target.y;
  const dz = camera.position.z - target.z;
  const distance = Math.hypot(dx, dy, dz);
  if (!finiteRange(distance, 0.01, 100_000)) return null;
  const view: CameraView = {
    target: [target.x, target.y, target.z],
    radius: distance * Math.tan((camera.fov * Math.PI) / 360),
    yaw: (Math.atan2(dx, dz) * 180) / Math.PI,
    pitch: (Math.asin(dy / distance) * 180) / Math.PI,
  };
  const encoded = formatCamera(view);
  return encoded ? parseCamera(encoded) : null;
}

export function show3d(
  graph: Camera3d | undefined,
  view: CameraView,
  duration = 0,
): void {
  if (!graph) return;
  const camera = graph.camera() as Camera;
  if (!camera.fov) return;
  const yaw = (view.yaw * Math.PI) / 180;
  const pitch = (view.pitch * Math.PI) / 180;
  const distance = view.radius / Math.tan((camera.fov * Math.PI) / 360);
  const level = Math.cos(pitch) * distance;
  const [x, y, z] = view.target;
  graph.cameraPosition(
    {
      x: x + Math.sin(yaw) * level,
      y: y + Math.sin(pitch) * distance,
      z: z + Math.cos(yaw) * level,
    },
    { x, y, z },
    duration,
  );
}

export function read2d(
  graph: Graph2d<GraphNode, GraphLink> | undefined,
  height: number,
): CameraView | null {
  if (!graph || height <= 0) return null;
  const center = graph.centerAt();
  const zoom = graph.zoom();
  const encoded = formatCamera({
    target: [center.x, center.y, 0],
    radius: height / (2 * zoom),
    yaw: 0,
    pitch: 0,
  });
  return encoded ? parseCamera(encoded) : null;
}

export function show2d(
  graph: Graph2d<GraphNode, GraphLink> | undefined,
  view: CameraView,
  height: number,
  duration = 0,
): void {
  if (!graph || height <= 0) return;
  graph.centerAt(view.target[0], view.target[1], duration);
  graph.zoom(height / (2 * view.radius), duration);
}

export function nodeCamera(view: CameraView, node: GraphNode): CameraView | null {
  if (![node.x, node.y, node.z ?? 0].every(Number.isFinite)) return null;
  return {
    ...view,
    target: [node.x!, node.y!, node.z ?? 0],
  };
}
