import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import type { Theme } from "../../hooks/theme";
import { applyLayout, layoutTicks, type LayoutMode } from "../../hooks/layout";
import { useQuality } from "../../hooks/quality";
import { graphEndpointId, graphKey } from "../../lib/graph";
import { showLink } from "../../lib/quality";
import { formatCamera, show2d, type CameraView } from "../../lib/camera";
import type { CloudData, CloudPick } from "../../lib/cloud";
import type { CloudMark } from "../../lib/focus";
import { makeOrder } from "../../lib/order";
import type { GraphData, GraphLink, GraphNode } from "../../types";
import { nodeTip } from "./Tip";
import { CloudPlane, type PlaneRef, type PlaneView } from "./Plane";

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
  cloud: CloudData | null;
  cloudHidden: boolean;
  cloudMark: CloudMark | null;
  onChoose: (node: GraphNode) => void;
  onCloudPick: (pick: CloudPick) => void;
  onPlane: (ready: boolean) => void;
  onFocus: (nodeId: string) => void;
  onClear: () => void;
};

function nodeSize(node: GraphNode): number {
  return Math.max(3.2, Math.sqrt(node.val) * 2.4);
}

export function pickRadius(value: number, scale: number): number {
  return Math.max(8 / Math.max(scale, Number.EPSILON), Math.sqrt(value) * 3);
}

export function pickDepth(
  node: GraphNode,
  event: MouseEvent,
  graph: FallbackRef["current"],
  canvas: HTMLCanvasElement | null,
): number {
  if (!graph || !canvas || node.x == null || node.y == null) {
    return Number.POSITIVE_INFINITY;
  }
  const point = graph.graph2ScreenCoords(node.x, node.y);
  const rect = canvas.getBoundingClientRect();
  return Math.hypot(
    event.clientX - rect.left - point.x,
    event.clientY - rect.top - point.y,
  );
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
  cloud,
  cloudHidden,
  cloudMark,
  onChoose,
  onCloudPick,
  onPlane,
  onFocus,
  onClear,
}: FallbackProps) {
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const restoredRef = useRef<string | null>(null);
  const planeRef = useRef<PlaneRef>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const order = useMemo(() => makeOrder(), []);
  const quality = useQuality(graph.nodes.length, width, height);
  const simple = graph.nodes.length >= 1_000;
  const topology = useMemo(() => graphKey(graph), [graph]);
  const activeIds = new Set(
    [selected?.id, hovered?.id].filter((id): id is string => Boolean(id)),
  );

  useEffect(() => {
    if (!graphRef.current) return;
    applyLayout(graphRef.current, layout);
  }, [graphRef, layout, simple, topology]);

  useEffect(() => {
    const key = formatCamera(camera);
    if (!camera || !key || restoredRef.current === key) return;
    restoredRef.current = key;
    show2d(graphRef.current, camera, height);
  }, [camera, graphRef, height]);

  useEffect(() => {
    setCanvas(
      wrapRef.current?.querySelector<HTMLCanvasElement>(".plane-force canvas") ?? null,
    );
  }, []);

  function planeView(view: PlaneView) {
    planeRef.current?.view({
      k: view.k,
      x: width / 2 - view.x * view.k,
      y: height / 2 - view.y * view.k,
    });
  }

  return (
    <div className="plane-stack" ref={wrapRef}>
      <CloudPlane
        ref={planeRef}
        active={!cloudHidden}
        canvas={canvas}
        data={cloud}
        height={height}
        onPick={onCloudPick}
        onReady={onPlane}
        order={order}
        theme={theme}
        width={width}
      />
      <div className="plane-force">
        <ForceGraph2D
          ref={graphRef}
          width={width}
          height={height}
          graphData={graph}
          backgroundColor="rgba(0,0,0,0)"
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
          cooldownTicks={layoutTicks(quality.cooldownTicks, simple)}
          d3VelocityDecay={0.28}
          nodeLabel={nodeTip}
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
          nodePointerAreaPaint={(node, color, context, scale) => {
            context.fillStyle = color;
            context.beginPath();
            context.arc(node.x!, node.y!, pickRadius(node.val, scale), 0, 2 * Math.PI);
            context.fill();
          }}
          onRenderFramePre={(context, scale) => {
            if (!cloudMark) return;
            context.beginPath();
            for (const target of cloudMark.targets) {
              context.moveTo(cloudMark.center[0], cloudMark.center[1]);
              context.lineTo(target.point[0], target.point[1]);
            }
            context.strokeStyle = theme === "dark" ? "#83b5bf" : "#4f7f89";
            context.globalAlpha = theme === "dark" ? 0.58 : 0.5;
            context.lineWidth = 1.2 / scale;
            context.stroke();
            context.globalAlpha = 1;
            context.beginPath();
            context.arc(
              cloudMark.center[0],
              cloudMark.center[1],
              3.4 / scale,
              0,
              Math.PI * 2,
            );
            context.fillStyle = theme === "dark" ? "#83b5bf" : "#4f7f89";
            context.fill();
          }}
          onNodeClick={(node, event) => {
            order.claim(3, pickDepth(node, event, graphRef.current, canvas), () => {
              planeRef.current?.drop();
              planeRef.current?.block();
              onChoose(node);
            });
            order.settle();
          }}
          onNodeHover={(node) => setHovered(node ?? null)}
          onNodeRightClick={(node) => onFocus(node.id)}
          onBackgroundClick={() => {
            if (!planeRef.current?.take()) onClear();
            order.settle();
          }}
          onZoom={planeView}
        />
      </div>
    </div>
  );
}
