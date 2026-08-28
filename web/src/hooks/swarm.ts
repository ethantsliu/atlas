import { useCallback, useEffect, useRef, useState } from "react";
import { type Camera } from "three";
import type { GraphRef } from "../components/map/Driver";
import { hitScreen } from "../lib/screen";
import { buildSwarm, markSwarm, swarmNode } from "../lib/swarm";
import type { GraphNode } from "../types";
import type { Theme } from "./theme";
import { bindChange } from "./control";
import type { PickOrder } from "../lib/order";

export type SwarmTip = {
  depth: number;
  id: string;
  label: string;
  x: number;
  y: number;
};

type SwarmClaim = {
  depth: number;
  node: GraphNode | null;
  x: number;
  y: number;
};
type SwarmDown = { x: number; y: number };
type ClaimRef = { current: boolean };

type SwarmInput = {
  graphRef: GraphRef;
  nodes: GraphNode[];
  selected: GraphNode | null;
  theme: Theme;
  onChoose: (node: GraphNode) => void;
  onFocus: (nodeId: string) => void;
  onHover: (node: GraphNode | null) => void;
  order: PickOrder;
};

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
    let frame = 0;
    let moved: PointerEvent | null = null;
    let down: SwarmDown | null = null;
    let pressed = false;
    let hovered: GraphNode | null = null;

    const hit = (event: PointerEvent | MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const camera = graph.camera() as Camera;
      const match = hitScreen(swarm, camera, rect, event.clientX, event.clientY);
      return {
        depth: match?.depth ?? Number.POSITIVE_INFINITY,
        node: swarmNode(swarm, match?.index),
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };
    };

    const show = (event: PointerEvent) => {
      const match = hit(event);
      if (match.node !== hovered) {
        hovered = match.node;
        hoverRef.current(hovered);
      }
      setTip(
        match.node
          ? {
              depth: match.depth,
              id: match.node.id,
              label: match.node.label,
              x: match.x,
              y: match.y,
            }
          : null,
      );
    };

    const clear = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      moved = null;
      hovered = null;
      setTip(null);
      hoverRef.current(null);
    };

    const move = (event: PointerEvent) => {
      if (pressed) {
        if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) {
          down = null;
        }
        clear();
        return;
      }
      moved = event;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (moved) show(moved);
      });
    };

    const leave = () => {
      down = null;
      pressed = false;
      clear();
    };
    const change = () => {
      clear();
    };

    const press = (event: PointerEvent) => {
      input.order.begin(event.timeStamp);
      claimRef.current = false;
      clear();
      if (!event.isPrimary || event.button !== 0) {
        down = null;
        pressed = false;
        return;
      }
      down = { x: event.clientX, y: event.clientY };
      pressed = true;
    };

    const choose = (event: MouseEvent | PointerEvent) => {
      const start = down;
      down = null;
      pressed = false;
      if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) {
        return;
      }
      const match = hit(event);
      const claim = { ...match, ...start };
      const node = pickSwarm(claim, event.clientX, event.clientY);
      if (!node) return;
      claimRef.current = true;
      input.order.claim(2, claim.depth, () => chooseRef.current(node));
    };

    const focus = (event: MouseEvent) => {
      const node = hit(event).node;
      if (!node) return;
      event.preventDefault();
      focusRef.current(node.id);
    };

    const dropChange = bindChange(graph.controls?.(), change);
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
      dropChange();
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
