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
import { useView } from "../../hooks/view";
import { useCore, type CoreTip } from "../../hooks/core";
import { useBegin } from "../../hooks/begin";
import {
  enableCursorZoom,
  FRAME_IDLE_WAIT,
  makeFrameIdle,
  type FrameControl,
  type FrameGraph,
  type FrameIdle,
} from "../../hooks/idle";
import { graphEndpointId, graphKey, largestGroup, splitPapers } from "../../lib/graph";
import { showLink } from "../../lib/quality";
import { formatCamera, type CameraView } from "../../lib/camera";
import { buildNode } from "../../lib/scene";
import { labelOf } from "../../lib/text";
import type { GraphData, GraphLink, GraphNode } from "../../types";
import type { CloudData, CloudPick } from "../../lib/cloud";
import type { CloudMark } from "../../lib/focus";
import { nodeDepth, usePoints, type PointTip } from "../../hooks/points";
import type { GraphRef } from "./Driver";
import { pickFront } from "./Front";
import { RouteMark } from "./Route";
import { frontRank, makeOrder } from "../../lib/order";

function useFrameIdle(graphRef: GraphRef) {
  const frameRef = useRef<FrameIdle | null>(null);
  useEffect(() => {
    const graph = graphRef.current as FrameGraph | undefined;
    if (!graph) return;
    const frame = makeFrameIdle(graph);
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const syncMotion = () => frame.motion(Boolean(motion?.matches));
    const syncVisibility = () => frame.visibility(document.hidden);
    syncMotion();
    syncVisibility();
    motion?.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    frameRef.current = frame;
    return () => {
      motion?.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
      if (frameRef.current === frame) frameRef.current = null;
      frame.dispose();
    };
  }, [graphRef]);
  return frameRef;
}

function useCursorZoom(
  graphRef: GraphRef,
  controlType: ReturnType<typeof cameraControl>,
) {
  useEffect(() => {
    if (controlType !== "orbit") return;
    let frame = 0;
    let active = true;
    const configure = () => {
      const control = graphRef.current?.controls() as FrameControl | undefined;
      if (enableCursorZoom(control) || !active) return;
      frame = window.requestAnimationFrame(configure);
    };
    configure();
    return () => {
      active = false;
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [controlType, graphRef]);
}

function useFrameTouch(frame: MutableRefObject<FrameIdle | null>, values: unknown[]) {
  useEffect(() => frame.current?.touch(), values);
}

function useFrameWake(frame: MutableRefObject<FrameIdle | null>, values: unknown[]) {
  useEffect(() => frame.current?.wake(), values);
}

function useFrameHover(frame: MutableRefObject<FrameIdle | null>, active: boolean) {
  useEffect(() => frame.current?.hover(active), [active, frame]);
}

function useCloudOpen(selected: boolean) {
  const open = useRef(selected);
  useEffect(() => {
    open.current = selected;
  }, [selected]);
  return open;
}

function stopFrames(
  frame: MutableRefObject<FrameIdle | null>,
  graph: GraphRef,
  camera: CameraView | null,
  fit: MutableRefObject<boolean>,
  showView: () => void,
  coreIds: Set<string>,
) {
  showView();
  if (camera || !fit.current) {
    frame.current?.engineStop();
    return;
  }
  fit.current = false;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const duration = layoutTime(Boolean(reduced), 700);
  graph.current?.zoomToFit(duration, 72, (node) => coreIds.has(node.id));
  frame.current?.engineStop(duration + FRAME_IDLE_WAIT);
}

type SpaceProps = {
  graph: GraphData;
  cloud: CloudData | null;
  cloudHidden: boolean;
  cloudSelected: boolean;
  cloudMark: CloudMark | null;
  graphRef: GraphRef;
  width: number;
  height: number;
  selected: GraphNode | null;
  theme: Theme;
  layout: LayoutMode;
  camera: CameraView | null;
  viewReady: boolean;
  onChoose: (node: GraphNode) => void;
  onCloudPick: (pick: CloudPick) => void;
  onFocus: (nodeId: string) => void;
  onClear: () => void;
};

export function cameraControl(width: number): "orbit" | "trackball" {
  return width <= 520 ? "trackball" : "orbit";
}

function PointTips({
  core,
  tip,
  cloud,
}: {
  core: CoreTip | null;
  tip: SwarmTip | null;
  cloud: PointTip | null;
}) {
  return (
    <>
      {core && (
        <div
          className="swarm-tip core-tip"
          data-depth={core.depth}
          role="tooltip"
          style={{ left: core.x + 14, top: core.y + 14 }}
        >
          {labelOf(core.node.kind)} · {core.node.label}
        </div>
      )}
      {tip && (
        <div
          className="swarm-tip"
          data-depth={tip.depth}
          role="tooltip"
          style={{ left: tip.x + 14, top: tip.y + 14 }}
        >
          Paper · {tip.label}
        </div>
      )}
      {cloud && (
        <div
          className="swarm-tip cloud-tip"
          data-depth={cloud.depth}
          role="tooltip"
          style={{ left: cloud.x + 14, top: cloud.y + 14 }}
        >
          {cloud.label}
        </div>
      )}
    </>
  );
}

function hoverFront(
  core: CoreTip | null,
  tip: SwarmTip | null,
  cloud: PointTip | null,
  probing: boolean,
) {
  if (probing) return 0;
  return frontRank([
    ...(core ? [{ depth: core.depth, rank: 3 as const }] : []),
    ...(tip ? [{ depth: tip.depth, rank: 2 as const }] : []),
    ...(cloud ? [{ depth: cloud.depth, rank: 1 as const }] : []),
  ]);
}

export function GraphSpace({
  graph,
  cloud,
  cloudHidden,
  cloudSelected,
  cloudMark,
  graphRef,
  width,
  height,
  selected,
  theme,
  layout,
  camera,
  viewReady,
  onChoose,
  onCloudPick,
  onFocus,
  onClear,
}: SpaceProps) {
  const [swarmHovered, setSwarmHovered] = useState<GraphNode | null>(null);
  const core = useCore(graphRef);
  const order = useMemo(() => makeOrder(), []);
  useBegin(graphRef, order);
  const quality = useQuality(graph.nodes.length + (cloud?.loaded ?? 0), width, height);
  const engineReadyRef = useRef(false);
  const fitRef = useRef(!camera);
  const fitKeyRef = useRef<string>();
  const controlType = useRef(cameraControl(width)).current;
  const showView = useView(graphRef, camera, viewReady);
  const frameRef = useFrameIdle(graphRef);
  useCursorZoom(graphRef, controlType);
  const cameraKey = formatCamera(camera);
  const cloudOpenRef = useCloudOpen(cloudSelected);
  const split = useMemo(() => splitPapers(graph), [graph]);
  const showSwarm = layout === "semantic" && split.papers.length >= 1_000;
  const sceneGraph = showSwarm ? split.core : graph;
  const swarmNodes = showSwarm ? split.papers : [];
  const coreIds = useMemo(() => largestGroup(sceneGraph), [sceneGraph]);
  const topology = useMemo(() => graphKey(sceneGraph), [sceneGraph]);
  const simple = graph.nodes.length >= 1_000;
  const makeNode = useCallback(
    (node: GraphNode) => buildNode(node, theme, quality.geometryDetail, simple),
    [quality.geometryDetail, simple, theme],
  );
  usePixel(graphRef, quality.pixelRatioCap);
  const cloudHit = usePoints({
    graphRef,
    data: layout === "semantic" ? cloud : null,
    active: !cloudHidden,
    detail: "full",
    theme,
    onPick: (pick) => {
      cloudOpenRef.current = true;
      onCloudPick(pick);
    },
    order,
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
      setSwarmHovered(node);
    },
    order,
  });
  const tip = swarmHit.tip;
  const hoverRank = hoverFront(core.tip, tip, cloudHit.tip, cloudHit.probing);
  const hovered =
    hoverRank === 3 ? (core.tip?.node ?? null) : hoverRank === 2 ? swarmHovered : null;
  useFrameHover(frameRef, cloudHit.probing || Boolean(cloudHit.tip));
  useMarks({
    graphRef,
    nodes: sceneGraph.nodes,
    selected,
    hovered,
    theme,
    detail: quality.geometryDetail,
    simple,
  });
  useEffect(() => {
    if (camera) {
      fitKeyRef.current = topology;
      fitRef.current = false;
      return;
    }
    if (fitKeyRef.current === topology) return;
    fitKeyRef.current = topology;
    fitRef.current = true;
  }, [camera, topology]);
  useEffect(() => {
    if (graphRef.current) {
      frameRef.current?.start();
      applyLayout(graphRef.current, layout, engineReadyRef.current);
      graphRef.current.refresh();
    }
  }, [graphRef, layout, simple, topology]);
  useFrameTouch(frameRef, [
    cloud?.loaded,
    cloudHidden,
    cloudMark,
    cameraKey,
    height,
    selected?.id,
    theme,
    topology,
    width,
  ]);
  useFrameWake(frameRef, [hovered?.id]);
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
        controlType={controlType}
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
        cooldownTicks={layoutTicks(quality.cooldownTicks, simple)}
        d3VelocityDecay={0.24}
        enableNodeDrag={false}
        onEngineTick={() => {
          enableCursorZoom(graphRef.current?.controls() as FrameControl | undefined);
          engineReadyRef.current = true;
          frameRef.current?.engineTick();
        }}
        onEngineStop={() =>
          stopFrames(frameRef, graphRef, camera, fitRef, showView, coreIds)
        }
        onNodeClick={(node) => {
          order.claim(3, nodeDepth(graphRef.current, node), () =>
            pickFront(cloudHit, cloudOpenRef, onChoose, node),
          );
          order.settle();
        }}
        onNodeHover={(node) => core.hover(node ?? null)}
        onNodeRightClick={(node) => onFocus(node.id)}
        onBackgroundClick={() => {
          if (!cloudOpenRef.current && !cloudHit.take() && !swarmHit.take()) {
            onClear();
          }
          order.settle();
        }}
      />
      <PointTips
        core={hoverRank === 3 ? core.tip : null}
        tip={hoverRank === 2 ? tip : null}
        cloud={hoverRank === 1 ? cloudHit.tip : null}
      />
      <RouteMark graphRef={graphRef} mark={cloudMark} theme={theme} />
    </>
  );
}
