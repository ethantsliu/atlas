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
  freeNodes,
  layoutTicks,
  layoutTime,
  pinNodes,
  type LayoutMode,
} from "../../hooks/layout";
import { useQuality } from "../../hooks/quality";
import { useRegions } from "../../hooks/regions";
import { usePixel } from "../../hooks/pixel";
import { useMarks } from "../../hooks/marks";
import { useScene } from "../../hooks/scene";
import type { Theme } from "../../hooks/theme";
import { graphEndpointId } from "../../lib/graph";
import { graphChrome, type ClusterSet } from "../../lib/clusters";
import { showCluster, showLink } from "../../lib/quality";
import { formatCamera, show3d, type CameraView } from "../../lib/camera";
import { buildNode } from "../../lib/scene";
import type { GraphData, GraphLink, GraphNode } from "../../types";
import type { GraphRef } from "./Driver";
import { RegionOverlay } from "./Regions";

type SpaceProps = {
  graph: GraphData;
  graphRef: GraphRef;
  width: number;
  height: number;
  selected: GraphNode | null;
  theme: Theme;
  layout: LayoutMode;
  camera: CameraView | null;
  clusters: ClusterSet;
  regionsEnabled: boolean;
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
  clusters,
  regionsEnabled,
  onChoose,
  onFocus,
  onClear,
}: SpaceProps) {
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const quality = useQuality(graph.nodes.length, width, height);
  const engineReadyRef = useRef(false);
  const fitRef = useRef(true);
  const fitFrameRef = useRef<number>();
  const timerRef = useRef<number>();
  const restoredRef = useRef<string | null>(null);
  const topology = useMemo(
    () =>
      graph.nodes
        .map((node) => node.id)
        .sort()
        .join("\u0000"),
    [graph.nodes],
  );
  const scene = useScene(graph, layout, quality.tier, selected?.id);
  const { ids: rendered, simple } = scene;
  const makeNode = useCallback(
    (node: GraphNode) => buildNode(node, theme, quality.geometryDetail, simple),
    [quality.geometryDetail, simple, theme],
  );
  const regionNodes = useMemo(() => [selected, hovered], [hovered, selected]);
  const activeRegion = selected?.id
    ? clusters.nodeClusters[selected.id]
    : hovered?.id
      ? clusters.nodeClusters[hovered.id]
      : null;
  const regionView = useRegions({
    graph,
    graphRef,
    clusters,
    active: regionNodes,
    quality,
    enabled: regionsEnabled,
  });
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
    fitRef.current = !selected;
  }, [graphRef, selected, topology]);

  useEffect(
    () => () => {
      window.cancelAnimationFrame(fitFrameRef.current ?? 0);
      window.clearTimeout(timerRef.current);
    },
    [],
  );

  useEffect(() => {
    if (graphRef.current) {
      const dense = layout === "semantic" && scene.simple;
      if (dense) pinNodes(scene.graph.nodes);
      else freeNodes(scene.graph.nodes);
      applyLayout(graphRef.current, layout, engineReadyRef.current, dense);
      graphRef.current.refresh();
    }
  }, [graphRef, layout, scene.graph.nodes, scene.simple]);

  useEffect(() => {
    const key = formatCamera(camera);
    if (!camera || !key || restoredRef.current === key || !graphRef.current) return;
    restoredRef.current = key;
    fitRef.current = false;
    show3d(graphRef.current, camera);
    regionView.project();
  }, [camera, graphRef, regionView]);

  useEffect(() => {
    if (camera || selected || layout !== "semantic" || !graphRef.current) return;
    const api = graphRef.current;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const duration = layoutTime(Boolean(reduced), 700);
    window.cancelAnimationFrame(fitFrameRef.current ?? 0);
    fitFrameRef.current = window.requestAnimationFrame(() => {
      fitRef.current = false;
      api.zoomToFit(duration, 72, (node) => !rendered || rendered.has(node.id));
    });
    return () => window.cancelAnimationFrame(fitFrameRef.current ?? 0);
  }, [camera, graphRef, layout, rendered, selected, topology]);

  const activeIds = useMemo(
    () => new Set([selected?.id, hovered?.id].filter(Boolean)),
    [hovered?.id, selected?.id],
  );

  return (
    <>
      <ForceGraph3D
        ref={graphRef as MutableRefObject<ForceGraphMethods<GraphNode, GraphLink>>}
        width={width}
        height={height}
        graphData={scene.graph}
        backgroundColor={theme === "dark" ? "#0f1511" : "#f0eadf"}
        showNavInfo={false}
        numDimensions={3}
        nodeLabel={(node) => node.label}
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
        cooldownTicks={layoutTicks(layout, quality.cooldownTicks, simple)}
        d3VelocityDecay={0.24}
        enableNodeDrag={false}
        onEngineTick={() => {
          engineReadyRef.current = true;
        }}
        onEngineStop={() => {
          if (!fitRef.current) {
            regionView.project();
            return;
          }
          fitRef.current = false;
          const reduced = window.matchMedia?.(
            "(prefers-reduced-motion: reduce)",
          ).matches;
          const duration = layoutTime(Boolean(reduced), 700);
          graphRef.current?.zoomToFit(duration, 72, () => true);
          window.clearTimeout(timerRef.current);
          timerRef.current = window.setTimeout(() => {
            regionView.markFit();
          }, duration + 30);
        }}
        onNodeClick={onChoose}
        onNodeHover={(node) => setHovered(node ?? null)}
        onNodeRightClick={(node) => onFocus(node.id)}
        onBackgroundClick={onClear}
      />
      <RegionOverlay
        points={regionView.points}
        view={{
          width,
          height,
          scale: regionView.scale,
          enabled:
            regionsEnabled &&
            showCluster(quality, regionView.scale, graph.nodes.length),
          activeId: activeRegion,
          reserved: [...regionView.reserved, ...graphChrome(width)],
        }}
      />
    </>
  );
}
