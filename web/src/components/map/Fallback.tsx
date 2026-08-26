import { useEffect, useRef, useState, type MutableRefObject } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import type { Theme } from "../../hooks/theme";
import {
  applyLayout,
  freeNodes,
  layoutTicks,
  pinNodes,
  type LayoutMode,
} from "../../hooks/layout";
import { useQuality } from "../../hooks/quality";
import { useScene } from "../../hooks/scene";
import { graphEndpointId } from "../../lib/graph";
import { showLink } from "../../lib/quality";
import { formatCamera, show2d, type CameraView } from "../../lib/camera";
import { labelOf } from "../../lib/text";
import type { GraphData, GraphLink, GraphNode } from "../../types";

export type FallbackRef = MutableRefObject<
  ForceGraphMethods<GraphNode, GraphLink> | undefined
>;

type FallbackProps = {
  graph: GraphData;
  graphRef: FallbackRef;
  width: number;
  height: number;
  selected: GraphNode | null;
  theme: Theme;
  layout: LayoutMode;
  camera: CameraView | null;
  onChoose: (node: GraphNode) => void;
  onFocus: (nodeId: string) => void;
  onClear: () => void;
};

function nodeSize(node: GraphNode): number {
  return Math.max(3.2, Math.sqrt(node.val) * 2.4);
}

function drawNode(node: GraphNode, context: CanvasRenderingContext2D, size: number) {
  const x = node.x!;
  const y = node.y!;
  context.beginPath();
  if (node.kind === "trick") {
    context.moveTo(x, y - size);
    context.lineTo(x + size, y);
    context.lineTo(x, y + size);
    context.lineTo(x - size, y);
    context.closePath();
  } else if (node.kind === "idea") {
    context.rect(x - size, y - size, size * 2, size * 2);
  } else {
    context.arc(x, y, node.kind === "paper" ? size * 0.82 : size, 0, Math.PI * 2);
  }
}

export function FallbackGraph({
  graph,
  graphRef,
  width,
  height,
  selected,
  theme,
  layout,
  camera,
  onChoose,
  onFocus,
  onClear,
}: FallbackProps) {
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const restoredRef = useRef<string | null>(null);
  const quality = useQuality(graph.nodes.length, width, height);
  const scene = useScene(graph, layout, quality.tier, selected?.id);
  const activeIds = new Set(
    [selected?.id, hovered?.id].filter((id): id is string => Boolean(id)),
  );

  useEffect(() => {
    if (!graphRef.current) return;
    const dense = layout === "semantic" && scene.simple;
    if (dense) pinNodes(scene.graph.nodes);
    else freeNodes(scene.graph.nodes);
    applyLayout(graphRef.current, layout, true, dense);
  }, [graphRef, layout, scene.graph.nodes, scene.simple]);

  useEffect(() => {
    const key = formatCamera(camera);
    if (!camera || !key || restoredRef.current === key) return;
    restoredRef.current = key;
    show2d(graphRef.current, camera, height);
  }, [camera, graphRef, height]);

  return (
    <ForceGraph2D
      ref={graphRef}
      width={width}
      height={height}
      graphData={scene.graph}
      backgroundColor={theme === "dark" ? "#0f1511" : "#f0eadf"}
      linkColor={() =>
        theme === "dark"
          ? `rgba(183,203,187,${quality.linkOpacity})`
          : `rgba(69,58,48,${quality.linkOpacity})`
      }
      linkVisibility={(link) => {
        if (layout === "connections") return true;
        const active =
          activeIds.has(graphEndpointId(link.source)) ||
          activeIds.has(graphEndpointId(link.target));
        return showLink(quality, { selected: active });
      }}
      linkWidth={layout === "connections" ? 0.8 : 1}
      cooldownTicks={layoutTicks(layout, quality.cooldownTicks, scene.simple)}
      d3VelocityDecay={0.28}
      nodeLabel={(node) => `${labelOf(node.kind)} · ${node.label}`}
      nodeCanvasObject={(node, context, scale) => {
        const size = nodeSize(node);
        drawNode(node, context, size);
        context.fillStyle = node.color;
        const emphasized = selected?.id === node.id || hovered?.id === node.id;
        context.shadowColor = node.color;
        context.shadowBlur = emphasized ? 14 : 3;
        context.fill();
        context.shadowBlur = 0;
        if (emphasized) {
          drawNode(node, context, size + 2 / scale);
          context.strokeStyle = theme === "dark" ? "#f4f0e7" : "#2d2722";
          context.lineWidth = 1.4 / scale;
          context.stroke();
        }
      }}
      nodePointerAreaPaint={(node, color, context) => {
        context.fillStyle = color;
        context.beginPath();
        context.arc(
          node.x!,
          node.y!,
          Math.max(8, Math.sqrt(node.val) * 3),
          0,
          2 * Math.PI,
        );
        context.fill();
      }}
      onNodeClick={onChoose}
      onNodeHover={(node) => setHovered(node ?? null)}
      onNodeRightClick={(node) => onFocus(node.id)}
      onBackgroundClick={onClear}
    />
  );
}
