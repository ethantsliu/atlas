import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import { applyLayout, layoutTime, type LayoutMode } from "../../hooks/layout";
import { useQuality } from "../../hooks/quality";
import { useRegions } from "../../hooks/regions";
import { usePixel } from "../../hooks/pixel";
import type { Theme } from "../../hooks/theme";
import { graphEndpointId, largestGroup } from "../../lib/graph";
import { graphChrome, type ClusterSet } from "../../lib/clusters";
import { showCluster, showLink } from "../../lib/quality";
import { buildNode, markNode } from "../../lib/scene";
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
  clusters,
  regionsEnabled,
  onChoose,
  onFocus,
  onClear,
}: SpaceProps) {
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const quality = useQuality(graph.nodes.length, width, height);
  const activeRef = useRef(new Set<string>());
  const engineReadyRef = useRef(false);
  const fitRef = useRef(true);
  const timerRef = useRef<number>();
  const coreIds = useMemo(() => largestGroup(graph), [graph]);
  const topology = useMemo(
    () =>
      graph.nodes
        .map((node) => node.id)
        .sort()
        .join("\u0000"),
    [graph.nodes],
  );
  const nodeById = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes],
  );
  const makeNode = useCallback(
    (node: GraphNode) =>
      buildNode(node, theme, quality.geometryDetail, quality.labelMaxChars),
    [quality.geometryDetail, quality.labelMaxChars, theme],
  );
  const regionNodes = useMemo(() => [selected, hovered], [hovered, selected]);
  const regionView = useRegions({
    graph,
    graphRef,
    clusters,
    active: regionNodes,
    quality,
    enabled: regionsEnabled,
  });
  usePixel(graphRef, quality.pixelRatioCap);

  useEffect(() => {
    fitRef.current = true;
  }, [graphRef, topology]);

  useEffect(
    () => () => {
      window.clearTimeout(timerRef.current);
    },
    [],
  );

  useEffect(() => {
    if (graphRef.current) {
      applyLayout(graphRef.current, layout, engineReadyRef.current);
    }
  }, [graphRef, layout]);

  useEffect(() => {
    const active = new Set(
      [selected?.id, hovered?.id].filter((id): id is string => Boolean(id)),
    );
    const changed = new Set([...activeRef.current, ...active]);
    for (const id of changed) {
      const node = nodeById.get(id);
      if (node) {
        markNode(
          node,
          active.has(id),
          theme,
          quality.geometryDetail,
          quality.labelMaxChars,
        );
      }
    }
    activeRef.current = active;
    graphRef.current?.refresh();
  }, [
    graphRef,
    hovered?.id,
    nodeById,
    quality.geometryDetail,
    quality.labelMaxChars,
    selected?.id,
    theme,
  ]);

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
        graphData={graph}
        backgroundColor={theme === "dark" ? "#0f1511" : "#f0eadf"}
        showNavInfo={false}
        numDimensions={3}
        nodeLabel={() => ""}
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
        cooldownTicks={quality.cooldownTicks}
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
          graphRef.current?.zoomToFit(duration, 72, (node) => coreIds.has(node.id));
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
          reserved: [...regionView.reserved, ...graphChrome(width)],
        }}
      />
    </>
  );
}
