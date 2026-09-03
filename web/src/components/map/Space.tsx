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
import { graphEndpointId, graphKey, largestGroup, splitPapers } from "../../lib/graph";
import { showLink } from "../../lib/quality";
import type { CameraView } from "../../lib/camera";
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

export const FRAME_IDLE_WAIT = 240;

type FrameControl = {
  addEventListener?: (type: string, listener: () => void) => void;
  removeEventListener?: (type: string, listener: () => void) => void;
  zoomToCursor?: boolean;
};

type FrameGraph = {
  controls: () => FrameControl;
  pauseAnimation: () => unknown;
  renderer: () => { domElement: HTMLCanvasElement };
  resumeAnimation: () => unknown;
};

type FrameTimer = {
  clear: (timer: number) => void;
  set: (callback: () => void, delay: number) => number;
};

type FrameLoop = {
  cancel: (frame: number) => void;
  request: (callback: () => void) => number;
};

export type FrameIdle = {
  dispose: () => void;
  engineStop: (delay?: number) => void;
  engineTick: () => void;
  start: () => void;
  touch: () => void;
};

export function enableCursorZoom(control: FrameControl | null | undefined): boolean {
  if (!control || !("zoomToCursor" in control)) return false;
  control.zoomToCursor = true;
  return true;
}

export function makeFrameIdle(
  graph: FrameGraph,
  timer: FrameTimer = {
    clear: (value) => window.clearTimeout(value),
    set: (callback, delay) => window.setTimeout(callback, delay),
  },
  loop: FrameLoop = {
    cancel: (value) => window.cancelAnimationFrame(value),
    request: (callback) => window.requestAnimationFrame(callback),
  },
): FrameIdle {
  const canvas = graph.renderer().domElement;
  const controls = graph.controls();
  enableCursorZoom(controls);
  let running = true;
  let paused = false;
  let pending = 0;
  let probeFrame = 0;
  const cancel = () => {
    if (pending) timer.clear(pending);
    pending = 0;
  };
  const resume = () => {
    cancel();
    if (!paused) return;
    paused = false;
    graph.resumeAnimation();
  };
  const rest = (delay = FRAME_IDLE_WAIT) => {
    cancel();
    if (running) return;
    pending = timer.set(() => {
      pending = 0;
      paused = true;
      graph.pauseAnimation();
    }, delay);
  };
  const start = () => {
    running = true;
    resume();
  };
  const touch = () => {
    resume();
    rest();
  };
  const probe = () => {
    if (probeFrame) return;
    touch();
    probeFrame = loop.request(() => {
      probeFrame = 0;
    });
  };
  const engineTick = () => {
    running = true;
    cancel();
  };
  const engineStop = (delay = FRAME_IDLE_WAIT) => {
    running = false;
    rest(delay);
  };
  const press = () => resume();
  const release = () => touch();
  controls.addEventListener?.("start", press);
  controls.addEventListener?.("change", touch);
  controls.addEventListener?.("end", release);
  canvas.addEventListener("pointermove", probe, true);
  canvas.addEventListener("pointerup", release, true);
  canvas.addEventListener("pointerleave", release, true);
  canvas.addEventListener("wheel", touch, true);
  return {
    dispose: () => {
      cancel();
      if (probeFrame) loop.cancel(probeFrame);
      probeFrame = 0;
      controls.removeEventListener?.("start", press);
      controls.removeEventListener?.("change", touch);
      controls.removeEventListener?.("end", release);
      canvas.removeEventListener("pointermove", probe, true);
      canvas.removeEventListener("pointerup", release, true);
      canvas.removeEventListener("pointerleave", release, true);
      canvas.removeEventListener("wheel", touch, true);
    },
    engineStop,
    engineTick,
    start,
    touch,
  };
}

function useFrameIdle(graphRef: GraphRef) {
  const frameRef = useRef<FrameIdle | null>(null);
  useEffect(() => {
    const graph = graphRef.current as FrameGraph | undefined;
    if (!graph) return;
    const frame = makeFrameIdle(graph);
    frameRef.current = frame;
    return () => {
      if (frameRef.current === frame) frameRef.current = null;
      frame.dispose();
    };
  }, [graphRef]);
  return frameRef;
}

function useCursorZoom(graphRef: GraphRef, width: number) {
  useEffect(() => {
    if (cameraControl(width) !== "orbit") return;
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
  }, [graphRef, width]);
}

function useFrameTouch(frame: MutableRefObject<FrameIdle | null>, values: unknown[]) {
  useEffect(() => frame.current?.touch(), values);
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
  const showView = useView(graphRef, camera, viewReady);
  const frameRef = useFrameIdle(graphRef);
  useCursorZoom(graphRef, width);
  const cloudOpenRef = useRef(cloudSelected);
  useEffect(() => {
    cloudOpenRef.current = cloudSelected;
  }, [cloudSelected]);
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
    height,
    hovered?.id,
    selected?.id,
    theme,
    topology,
    width,
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
        graphData={sceneGraph}
        backgroundColor={theme === "dark" ? "#0f1511" : "#f0eadf"}
        showNavInfo={false}
        controlType={cameraControl(width)}
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
