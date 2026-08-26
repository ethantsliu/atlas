import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import {
  applyLayout,
  layoutTicks,
  layoutTime,
  type LayoutMode,
} from "../../hooks/layout";
import { useQuality } from "../../hooks/quality";
import { usePixel } from "../../hooks/pixel";
import { useMarks } from "../../hooks/marks";
import type { Theme } from "../../hooks/theme";
import { graphEndpointId, largestGroup } from "../../lib/graph";
import { showLink } from "../../lib/quality";
import { formatCamera, show3d, type CameraView } from "../../lib/camera";
import { buildNode } from "../../lib/scene";
import { labelOf } from "../../lib/text";
import type { GraphData, GraphLink, GraphNode } from "../../types";
import type { GraphRef } from "./Driver";

type SpaceProps = {
  graph: GraphData;
  graphRef: GraphRef;
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

export function GraphSpace({
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
}: SpaceProps) {
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const quality = useQuality(graph.nodes.length, width, height);
  const engineReadyRef = useRef(false);
  const fitRef = useRef(true);
  const fitKeyRef = useRef<string>();
  const restoredRef = useRef<string | null>(null);
  const coreIds = useMemo(() => largestGroup(graph), [graph]);
  const topology = useMemo(
    () =>
      graph.nodes
        .map((node) => node.id)
        .sort()
        .join("\u0000"),
    [graph.nodes],
  );
  const simple = graph.nodes.length >= 1_000;
  const makeNode = useCallback(
    (node: GraphNode) => buildNode(node, theme, quality.geometryDetail, simple),
    [quality.geometryDetail, simple, theme],
  );
  usePixel(graphRef, quality.pixelRatioCap);
  useMarks({
    graphRef,
    nodes: graph.nodes,
    selected,
    hovered,
    theme,
    detail: quality.geometryDetail,
    simple,
  });

  useEffect(() => {
    if (camera) {
      fitRef.current = false;
      return;
    }
    if (fitKeyRef.current === topology) return;
    fitKeyRef.current = topology;
    fitRef.current = true;
  }, [camera, selected, topology]);

  useEffect(() => {
    if (graphRef.current) {
      applyLayout(graphRef.current, layout, engineReadyRef.current);
      graphRef.current.refresh();
    }
  }, [graph.nodes, graphRef, layout, simple]);

  useEffect(() => {
    const key = formatCamera(camera);
    if (!camera || !key || restoredRef.current === key || !graphRef.current) return;
    restoredRef.current = key;
    fitRef.current = false;
    show3d(graphRef.current, camera);
  }, [camera, graphRef]);

  const activeIds = useMemo(
    () => new Set([selected?.id, hovered?.id].filter(Boolean)),
    [hovered?.id, selected?.id],
  );

  return (
    <ForceGraph3D
      ref={graphRef as MutableRefObject<ForceGraphMethods<GraphNode, GraphLink>>}
      width={width}
      height={height}
      graphData={graph}
      backgroundColor={theme === "dark" ? "#0f1511" : "#f0eadf"}
      showNavInfo={false}
      numDimensions={3}
      nodeLabel={(node) => `${labelOf(node.kind)} · ${node.label}`}
      nodeThreeObject={makeNode}
      linkColor={() => (theme === "dark" ? "#617065" : "#9d9285")}
      linkWidth={0}
      linkVisibility={(link) => {
        if (layout === "connections") return true;
        const active =
          activeIds.has(graphEndpointId(link.source)) ||
          activeIds.has(graphEndpointId(link.target));
        return showLink(quality, { selected: active });
      }}
      linkOpacity={
        layout === "connections"
          ? Math.max(0.12, quality.linkOpacity)
          : quality.linkOpacity
      }
      cooldownTicks={layoutTicks(quality.cooldownTicks, simple)}
      d3VelocityDecay={0.24}
      enableNodeDrag={false}
      onEngineTick={() => {
        engineReadyRef.current = true;
      }}
      onEngineStop={() => {
        if (!fitRef.current) return;
        fitRef.current = false;
        const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        const duration = layoutTime(Boolean(reduced), 700);
        graphRef.current?.zoomToFit(duration, 72, (node) => coreIds.has(node.id));
      }}
      onNodeClick={onChoose}
      onNodeHover={(node) => setHovered(node ?? null)}
      onNodeRightClick={(node) => onFocus(node.id)}
      onBackgroundClick={onClear}
    />
  );
}
