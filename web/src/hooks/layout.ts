import { useState } from "react";
import type { ForceGraphMethods } from "react-force-graph-3d";
import type { ForceGraphMethods as ForceGraph2D } from "react-force-graph-2d";
import { pullCenter } from "../lib/force";
import type { GraphLink, GraphNode } from "../types";

export type LayoutMode = "semantic" | "connections";

export type LayoutSpec = {
  anchor: number;
  center: number;
  charge: number;
  distance: number;
  link: number;
};

export type LayoutGraph =
  | Pick<ForceGraphMethods<GraphNode, GraphLink>, "d3Force" | "d3ReheatSimulation">
  | Pick<ForceGraph2D<GraphNode, GraphLink>, "d3Force" | "d3ReheatSimulation">;

const SPECS: Record<LayoutMode, LayoutSpec> = {
  semantic: {
    anchor: 0.11,
    center: 0.015,
    charge: -24,
    distance: 52,
    link: 0.08,
  },
  connections: {
    anchor: 0,
    center: 0.04,
    charge: -52,
    distance: 34,
    link: 0.72,
  },
};

export function layoutSpec(mode: LayoutMode): LayoutSpec {
  return SPECS[mode];
}

export function layoutTime(reduced: boolean, duration = 450): number {
  return reduced ? 0 : duration;
}

export function layoutTicks(mode: LayoutMode, ticks: number, dense = false): number {
  if (mode === "semantic") return 0;
  return dense ? Math.min(ticks, 30) : ticks;
}

export function pinNodes(nodes: GraphNode[]): void {
  for (const node of nodes) {
    const x = node.sx ?? node.x;
    const y = node.sy ?? node.y;
    const z = node.sz ?? node.z;
    if (x == null || y == null) continue;
    node.x = x;
    node.y = y;
    node.z = z ?? 0;
    node.fx = x;
    node.fy = y;
    node.fz = z ?? 0;
    node.vx = 0;
    node.vy = 0;
    node.vz = 0;
  }
}

export function freeNodes(nodes: GraphNode[]): void {
  for (const node of nodes) {
    delete node.fx;
    delete node.fy;
    delete node.fz;
  }
}

export function applyLayout(graph: LayoutGraph, mode: LayoutMode, reheat = true): void {
  const spec = layoutSpec(mode);
  const target = graph as Pick<
    ForceGraphMethods<GraphNode, GraphLink>,
    "d3Force" | "d3ReheatSimulation"
  >;
  target.d3Force("atlas-center", mode === "semantic" ? null : pullCenter(spec.center));
  target.d3Force("atlas-semantic", null);
  target.d3Force("link")?.strength?.(mode === "semantic" ? 0 : spec.link);
  target.d3Force("link")?.distance?.(spec.distance);
  target.d3Force("charge")?.strength?.(mode === "semantic" ? 0 : spec.charge);
  if (reheat && mode === "connections") target.d3ReheatSimulation();
}

export function useLayout(initial: LayoutMode = "semantic") {
  return useState<LayoutMode>(initial);
}
