import { useCallback, useEffect, useRef, useState } from "react";
import { Raycaster, Vector2, type Camera } from "three";
import type { GraphRef } from "../components/map/Driver";
import { buildSwarm, markSwarm, swarmNode } from "../lib/swarm";
import type { GraphNode } from "../types";
import type { Theme } from "./theme";

export type SwarmTip = { id: string; label: string; x: number; y: number };

type SwarmMark = { node: GraphNode; x: number; y: number };
type SwarmClaim = { node: GraphNode | null; x: number; y: number };
type ClaimRef = { current: boolean };

type SwarmInput = {
  graphRef: GraphRef;
  nodes: GraphNode[];
  selected: GraphNode | null;
  theme: Theme;
  onChoose: (node: GraphNode) => void;
  onFocus: (nodeId: string) => void;
  onHover: (node: GraphNode | null) => void;
};

export function bindSwarm(
  target: SwarmMark | null,
  fallback: GraphNode | null,
  x: number,
  y: number,
): SwarmClaim {
  const nearby = target && Math.hypot(x - target.x, y - target.y) <= 10;
  return { node: nearby ? target.node : fallback, x, y };
}

export function pickSwarm(
  claim: SwarmClaim | null,
  x: number,
  y: number,
): GraphNode | null {
  if (!claim || Math.hypot(x - claim.x, y - claim.y) > 5) return null;
  return claim.node;
}

export function takeSwarm(claim: ClaimRef): boolean {
  const taken = claim.current;
  claim.current = false;
  return taken;
}

export function useSwarm(input: SwarmInput): {
  tip: SwarmTip | null;
  take: () => boolean;
} {
  const [tip, setTip] = useState<SwarmTip | null>(null);
  const swarmRef = useRef<ReturnType<typeof buildSwarm>>();
  const claimRef = useRef(false);
  const chooseRef = useRef(input.onChoose);
  const focusRef = useRef(input.onFocus);
  const hoverRef = useRef(input.onHover);
  chooseRef.current = input.onChoose;
  focusRef.current = input.onFocus;
  hoverRef.current = input.onHover;
  const take = useCallback(() => takeSwarm(claimRef), []);

  useEffect(() => {
    const graph = input.graphRef.current;
    if (!graph || input.nodes.length === 0) return;
    const swarm = buildSwarm(input.nodes, input.theme);
    swarmRef.current = swarm;
    graph.scene().add(swarm);
    const canvas = graph.renderer().domElement;
    const raycaster = new Raycaster();
    const pointer = new Vector2();
    let frame = 0;
    let moved: PointerEvent | null = null;
    let down: SwarmClaim | null = null;
    let hovered: GraphNode | null = null;
    let target: SwarmMark | null = null;

    const hit = (event: PointerEvent | MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      );
      const camera = graph.camera() as Camera;
      raycaster.params.Points = {
        threshold: Math.max(2.5, camera.position.length() / 180),
      };
      raycaster.setFromCamera(pointer, camera);
      const match = raycaster.intersectObject(swarm, false)[0];
      return {
        node: swarmNode(swarm, match?.index),
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };
    };

    const show = (event: PointerEvent) => {
      const match = hit(event);
      target = match.node
        ? { node: match.node, x: event.clientX, y: event.clientY }
        : null;
      if (match.node !== hovered) {
        hovered = match.node;
        hoverRef.current(hovered);
      }
      setTip(
        match.node
          ? { id: match.node.id, label: match.node.label, x: match.x, y: match.y }
          : null,
      );
    };

    const move = (event: PointerEvent) => {
      moved = event;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (moved) show(moved);
      });
    };

    const leave = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      moved = null;
      hovered = null;
      target = null;
      setTip(null);
      hoverRef.current(null);
    };

    const press = (event: PointerEvent) => {
      claimRef.current = false;
      if (!event.isPrimary || event.button !== 0) {
        down = null;
        return;
      }
      const nearby =
        target && Math.hypot(event.clientX - target.x, event.clientY - target.y) <= 10;
      const fallback = nearby ? null : hit(event).node;
      down = bindSwarm(target, fallback, event.clientX, event.clientY);
    };

    const choose = (event: MouseEvent | PointerEvent) => {
      const node = pickSwarm(down, event.clientX, event.clientY);
      down = null;
      if (!node) return;
      claimRef.current = true;
      chooseRef.current(node);
    };

    const focus = (event: MouseEvent) => {
      const node = hit(event).node;
      if (!node) return;
      event.preventDefault();
      focusRef.current(node.id);
    };

    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerleave", leave);
    canvas.addEventListener("pointerdown", press);
    window.addEventListener("pointerup", choose, true);
    window.addEventListener("mouseup", choose, true);
    canvas.addEventListener("click", choose, true);
    canvas.addEventListener("contextmenu", focus);
    return () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerleave", leave);
      canvas.removeEventListener("pointerdown", press);
      window.removeEventListener("pointerup", choose, true);
      window.removeEventListener("mouseup", choose, true);
      canvas.removeEventListener("click", choose, true);
      canvas.removeEventListener("contextmenu", focus);
      if (frame) cancelAnimationFrame(frame);
      graph.scene().remove(swarm);
      swarm.geometry.dispose();
      swarm.material.dispose();
      swarmRef.current = undefined;
      hoverRef.current(null);
    };
  }, [input.graphRef, input.nodes, input.theme]);

  useEffect(() => {
    const swarm = swarmRef.current;
    if (!swarm) return;
    markSwarm(swarm, input.selected?.id ?? null, tip?.id ?? null);
  }, [input.selected?.id, tip?.id]);

  return { tip, take };
}
