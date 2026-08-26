import { useEffect, useRef, useState } from "react";
import { Raycaster, Vector2, type Camera } from "three";
import type { GraphRef } from "../components/map/Driver";
import { buildSwarm, markSwarm, swarmNode } from "../lib/swarm";
import type { GraphNode } from "../types";
import type { Theme } from "./theme";

export type SwarmTip = { id: string; label: string; x: number; y: number };

type SwarmInput = {
  graphRef: GraphRef;
  nodes: GraphNode[];
  selected: GraphNode | null;
  theme: Theme;
  onChoose: (node: GraphNode) => void;
  onFocus: (nodeId: string) => void;
  onHover: (node: GraphNode | null) => void;
};

export function useSwarm(input: SwarmInput): SwarmTip | null {
  const [tip, setTip] = useState<SwarmTip | null>(null);
  const swarmRef = useRef<ReturnType<typeof buildSwarm>>();
  const chooseRef = useRef(input.onChoose);
  const focusRef = useRef(input.onFocus);
  const hoverRef = useRef(input.onHover);
  chooseRef.current = input.onChoose;
  focusRef.current = input.onFocus;
  hoverRef.current = input.onHover;

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
    let down: [number, number] | null = null;
    let hovered: GraphNode | null = null;

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
      setTip(null);
      hoverRef.current(null);
    };

    const press = (event: PointerEvent) => {
      down = [event.clientX, event.clientY];
    };

    const choose = (event: MouseEvent) => {
      if (down && Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5) {
        return;
      }
      const node = hit(event).node;
      if (node) chooseRef.current(node);
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
    canvas.addEventListener("click", choose);
    canvas.addEventListener("contextmenu", focus);
    return () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerleave", leave);
      canvas.removeEventListener("pointerdown", press);
      canvas.removeEventListener("click", choose);
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

  return tip;
}
