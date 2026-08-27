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
import { useSwarm, type SwarmTip } from "../../hooks/swarm";
import type { Theme } from "../../hooks/theme";
import { graphEndpointId, largestGroup, splitPapers } from "../../lib/graph";
import { showLink } from "../../lib/quality";
import { formatCamera, show3d, type CameraView } from "../../lib/camera";
import { buildNode } from "../../lib/scene";
import { labelOf } from "../../lib/text";
import type { GraphData, GraphLink, GraphNode } from "../../types";
import type { CloudData, CloudPaper } from "../../lib/cloud";
import { usePoints, type PointTip } from "../../hooks/points";
import type { GraphRef } from "./Driver";
import { pickFront } from "./Front";

type SpaceProps = {
  graph: GraphData;
  cloud: CloudData | null;
  cloudSelected: boolean;
  graphRef: GraphRef;
  width: number;
  height: number;
  selected: GraphNode | null;
  theme: Theme;
  layout: LayoutMode;
  camera: CameraView | null;
  onChoose: (node: GraphNode) => void;
  onCloudPick: (paper: CloudPaper) => void;
  onFocus: (nodeId: string) => void;
  onClear: () => void;
};

function PointTips({ tip, cloud }: { tip: SwarmTip | null; cloud: PointTip | null }) {
  return (
    <>
      {tip && (
        <div
          className="swarm-tip"
          role="tooltip"
          style={{ left: tip.x + 14, top: tip.y + 14 }}
        >
          Paper · {tip.label}
        </div>
      )}
      {cloud && (
        <div
          className="swarm-tip cloud-tip"
          role="tooltip"
          style={{ left: cloud.x + 14, top: cloud.y + 14 }}
        >
          {cloud.label}
        </div>
      )}
    </>
  );
}

export function GraphSpace({
  graph,
  cloud,
  cloudSelected,
  graphRef,
  width,
  height,
  selected,
  theme,
  layout,
  camera,
  onChoose,
  onCloudPick,
  onFocus,
  onClear,
}: SpaceProps) {
  const [coreHovered, setCoreHovered] = useState<GraphNode | null>(null);
  const [swarmHovered, setSwarmHovered] = useState<GraphNode | null>(null);
  const hovered = swarmHovered ?? coreHovered;
  const quality = useQuality(
    graph.nodes.length + (cloud?.scopes.length ?? 0),
    width,
    height,
  );
  const engineReadyRef = useRef(false);
  const fitRef = useRef(true);
  const fitKeyRef = useRef<string>();
  const restoredRef = useRef<string | null>(null);
  const cloudOpenRef = useRef(cloudSelected);
  useEffect(() => {
    cloudOpenRef.current = cloudSelected;
  }, [cloudSelected]);
  const split = useMemo(() => splitPapers(graph), [graph]);
  const showSwarm = layout === "semantic" && split.papers.length >= 1_000;
  const sceneGraph = showSwarm ? split.core : graph;
  const swarmNodes = showSwarm ? split.papers : [];
  const coreIds = useMemo(() => largestGroup(sceneGraph), [sceneGraph]);
  const topology = useMemo(
    () =>
      sceneGraph.nodes
        .map((node) => node.id)
        .sort()
        .join("\u0000"),
    [sceneGraph.nodes],
  );
  const simple = graph.nodes.length >= 1_000;
  const makeNode = useCallback(
    (node: GraphNode) => buildNode(node, theme, quality.geometryDetail, simple),
    [quality.geometryDetail, simple, theme],
  );
  usePixel(graphRef, quality.pixelRatioCap);
  const cloudHit = usePoints({
    graphRef,
    data: layout === "semantic" ? cloud : null,
    theme,
    onPick: (paper) => {
      cloudOpenRef.current = true;
      onCloudPick(paper);
    },
  });
  useMarks({
    graphRef,
    nodes: sceneGraph.nodes,
    selected,
    hovered,
    theme,
    detail: quality.geometryDetail,
    simple,
  });
  const swarmHit = useSwarm({
    graphRef,
    nodes: swarmNodes,
    selected,
    theme,
    onChoose: (node) => {
      pickFront(cloudHit, cloudOpenRef, onChoose, node);
    },
    onFocus,
    onHover: (node) => {
      cloudHit.mute(Boolean(node));
      setSwarmHovered(node);
    },
  });
  const tip = swarmHit.tip;

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
    <>
      <ForceGraph3D
        ref={graphRef as MutableRefObject<ForceGraphMethods<GraphNode, GraphLink>>}
        width={width}
        height={height}
        graphData={sceneGraph}
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
          const reduced = window.matchMedia?.(
            "(prefers-reduced-motion: reduce)",
          ).matches;
          const duration = layoutTime(Boolean(reduced), 700);
          graphRef.current?.zoomToFit(duration, 72, (node) => coreIds.has(node.id));
        }}
        onNodeClick={(node) => {
          if (swarmHit.take()) return;
          pickFront(cloudHit, cloudOpenRef, onChoose, node);
        }}
        onNodeHover={(node) => {
          if (node) cloudHit.block();
          setCoreHovered(node ?? null);
        }}
        onNodeRightClick={(node) => onFocus(node.id)}
        onBackgroundClick={() => {
          if (!cloudOpenRef.current && !cloudHit.take() && !swarmHit.take()) {
            onClear();
          }
        }}
      />
      <PointTips tip={tip} cloud={cloudHit.tip} />
    </>
  );
}
