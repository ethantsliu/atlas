import {
  lazy,
  Suspense,
  useCallback,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { layoutTime, type LayoutMode } from "../../hooks/layout";
import { useElementSize } from "../../hooks/size";
import type { Theme } from "../../hooks/theme";
import { useWebgl } from "../../hooks/webgl";
import { findNextNode, type ArrowKey } from "../../lib/nav";
import type { CameraView } from "../../lib/camera";
import type { GraphData, GraphNode } from "../../types";
import type { CloudData } from "../../lib/cloud";
import type { CloudPick } from "../../lib/cloud";
import type { CloudMark } from "../../lib/focus";
import { GraphControls, type RenderMode } from "./Controls";
import type { GraphRef } from "./Driver";
import type { FallbackRef } from "./Fallback";
import { WebglStatus } from "./Status";
import { EmptyState, ResultStatus } from "../shared/Empty";
import { GraphTools } from "./Tools";
import { GraphHelp } from "./Help";
import { GraphLegend } from "./Legend";

const GraphFallback = lazy(() =>
  import("./Fallback").then((module) => ({ default: module.FallbackGraph })),
);

const GraphSpace = lazy(() =>
  import("./Space").then((module) => ({ default: module.GraphSpace })),
);

type GraphCanvasProps = {
  graph: GraphData;
  cloud: CloudData | null;
  cloudHidden: boolean;
  cloudLabel: string | null;
  cloudSelected: boolean;
  cloudMark: CloudMark | null;
  selected: GraphNode | null;
  onChoose: (node: GraphNode) => void;
  onCloudPick: (pick: CloudPick) => void;
  onFocus: (nodeId: string) => void;
  onClearSelection: () => void;
  onReset: () => void;
  query: string;
  theme: Theme;
  layout: LayoutMode;
  render: RenderMode;
  shareUrl: (camera?: CameraView | null, render?: RenderMode) => string;
  onLayout: (mode: LayoutMode) => void;
  onRender: (mode: RenderMode) => void;
  camera: CameraView | null;
  cameraReady: boolean;
  viewReady: boolean;
};

function selectedValue(graph: GraphData, selected: GraphNode | null): string {
  return graph.nodes.some((node) => node.id === selected?.id)
    ? (selected?.id ?? "")
    : "";
}

function nodeCount(
  graph: GraphData,
  cloud: CloudData | null,
  cloudHidden: boolean,
  mark: CloudMark | null,
  cloudReady: boolean,
): number {
  return (
    graph.nodes.length +
    (cloudReady && !cloudHidden ? (cloud?.loaded ?? 0) : 0) +
    (cloudReady && mark ? 1 : 0)
  );
}

function arrowNode(
  event: KeyboardEvent<HTMLElement>,
  graph: GraphData,
  graphRef: GraphRef | FallbackRef,
  selected: GraphNode | null,
): GraphNode | null {
  if (event.target !== event.currentTarget || !event.key.startsWith("Arrow")) {
    return null;
  }
  event.preventDefault();
  const projector = graphRef.current;
  const projected = graph.nodes.map((node) => {
    if (!projector || node.x == null || node.y == null || node.z == null) return node;
    const point = projector.graph2ScreenCoords(node.x, node.y, node.z);
    return { ...node, x: point.x, y: point.y };
  });
  const current = selected
    ? (projected.find((node) => node.id === selected.id) ?? null)
    : null;
  const next = findNextNode(projected, current, event.key as ArrowKey);
  return graph.nodes.find((node) => node.id === next?.id) ?? null;
}

function resetGraphView(
  mode: RenderMode,
  graph: GraphRef,
  fallback: FallbackRef,
): void {
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const duration = layoutTime(Boolean(reduced), 700);
  if (mode === "3d") {
    if (!graph.current?.atlasFitCloud?.(duration)) {
      graph.current?.zoomToFit(duration, 72);
    }
  } else {
    fallback.current?.zoomToFit(duration, 72);
  }
}

function chooseGraphNode(
  node: GraphNode,
  onChoose: (node: GraphNode) => void,
  target: HTMLElement | null,
): void {
  onChoose(node);
  target?.focus({ preventScroll: true });
}

type GraphViewportProps = Pick<
  GraphCanvasProps,
  | "camera"
  | "cameraReady"
  | "cloud"
  | "cloudHidden"
  | "cloudMark"
  | "cloudSelected"
  | "graph"
  | "layout"
  | "onChoose"
  | "onCloudPick"
  | "onFocus"
  | "selected"
  | "theme"
> & {
  fallbackRef: FallbackRef;
  graphRef: GraphRef;
  hasContent: boolean;
  height: number;
  mode: RenderMode;
  onClear: () => void;
  onPlane: (ready: boolean) => void;
  target: HTMLElement | null;
  top: number;
  width: number;
};

function GraphViewport(props: GraphViewportProps) {
  const {
    camera,
    cameraReady,
    cloud,
    cloudHidden,
    cloudMark,
    cloudSelected,
    fallbackRef,
    graph,
    graphRef,
    hasContent,
    height,
    layout,
    mode,
    onChoose,
    onClear,
    onCloudPick,
    onFocus,
    onPlane,
    selected,
    target,
    theme,
    top,
    width,
  } = props;
  const choose = (node: GraphNode) => chooseGraphNode(node, onChoose, target);
  const visible = hasContent && width > 0 && height > 0;
  return (
    <div className="graph-viewport" style={{ top }}>
      {mode === "3d" && visible && (
        <Suspense fallback={null}>
          <GraphSpace
            graph={graph}
            cloud={cloud}
            cloudHidden={cloudHidden}
            cloudSelected={cloudSelected}
            cloudMark={cloudMark}
            graphRef={graphRef}
            width={width}
            height={height}
            selected={selected}
            theme={theme}
            layout={layout}
            camera={camera}
            idleReady={!selected}
            viewReady={cameraReady}
            onChoose={choose}
            onCloudPick={onCloudPick}
            onFocus={onFocus}
            onClear={onClear}
          />
        </Suspense>
      )}
      {mode === "2d" && visible && (
        <Suspense fallback={null}>
          <GraphFallback
            graph={graph}
            cloud={cloud}
            cloudHidden={cloudHidden}
            cloudMark={cloudMark}
            graphRef={fallbackRef}
            width={width}
            height={height}
            selected={selected}
            theme={theme}
            layout={layout}
            camera={camera}
            onChoose={choose}
            onCloudPick={onCloudPick}
            onPlane={onPlane}
            onFocus={onFocus}
            onClear={onClear}
          />
        </Suspense>
      )}
    </div>
  );
}

export function GraphCanvas({
  graph,
  cloud,
  cloudHidden,
  cloudLabel,
  cloudSelected,
  cloudMark,
  selected,
  onChoose,
  onCloudPick,
  onFocus,
  onClearSelection,
  onReset,
  query,
  theme,
  layout,
  render,
  shareUrl,
  onLayout,
  onRender,
  camera,
  cameraReady,
  viewReady,
}: GraphCanvasProps) {
  const { ref: containerRef, width, height } = useElementSize<HTMLElement>();
  const { ref: chromeRef, height: chromeHeight } = useElementSize<HTMLDivElement>();
  const { mode, status, retry } = useWebgl(containerRef, render);
  const graphRef = useRef<GraphRef["current"]>();
  const fallbackRef = useRef<FallbackRef["current"]>();
  const [planeReady, setPlaneReady] = useState(false);
  const selectedId = selectedValue(graph, selected);
  const cloudReady = mode === "3d" || planeReady;
  const visibleCount = nodeCount(graph, cloud, cloudHidden, cloudMark, cloudReady);
  const hasContent = visibleCount > 0;
  const viewportTop = chromeHeight ? chromeHeight + 24 : width <= 480 ? 268 : 100;
  const viewportHeight = Math.max(0, height - viewportTop);
  const archive = Boolean(
    cloudReady && !cloudHidden && cloud?.loaded && layout === "semantic",
  );
  const resetView = useCallback(
    () => resetGraphView(mode, graphRef, fallbackRef),
    [fallbackRef, graphRef, mode],
  );

  return (
    <>
      <ResultStatus
        count={visibleCount}
        label="visible graph node"
        live={viewReady}
        query={query}
      />
      <section
        className="graph-wrap"
        ref={containerRef}
        aria-label={`Interactive ${mode === "3d" ? "3D " : ""}research graph`}
        aria-describedby="graph-help"
        tabIndex={0}
        onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
          const activeRef = mode === "3d" ? graphRef : fallbackRef;
          const source = arrowNode(event, graph, activeRef, selected);
          if (source) onChoose(source);
        }}
      >
        <GraphHelp cloudLabel={cloudLabel} selected={selected} />
        <div className="graph-chrome" ref={chromeRef}>
          <GraphControls
            count={visibleCount}
            mode={mode}
            layout={layout}
            onReset={resetView}
          >
            <GraphTools
              graphRef={graphRef}
              fallbackRef={fallbackRef}
              height={viewportHeight}
              layout={layout}
              mode={mode}
              render={render}
              nodes={graph.nodes}
              onChoose={onChoose}
              onLayout={onLayout}
              onRender={onRender}
              selected={selected}
              selectedId={selectedId}
              shareUrl={shareUrl}
            />
          </GraphControls>
        </div>
        <WebglStatus status={status} requested={render} onRetry={retry} />
        {!hasContent && viewReady && (
          <EmptyState
            title={
              query.trim()
                ? `No graph nodes match “${query.trim()}”`
                : "No graph nodes are visible"
            }
            copy="Clear the search and restore the default lenses to continue exploring."
            action="Reset map"
            onReset={onReset}
          />
        )}
        <GraphViewport
          graph={graph}
          cloud={cloud}
          cloudHidden={cloudHidden}
          cloudSelected={cloudSelected}
          cloudMark={cloudMark}
          fallbackRef={fallbackRef}
          graphRef={graphRef}
          hasContent={hasContent}
          width={width}
          height={viewportHeight}
          top={viewportTop}
          mode={mode}
          selected={selected}
          theme={theme}
          layout={layout}
          camera={camera}
          cameraReady={cameraReady}
          target={containerRef.current}
          onChoose={onChoose}
          onCloudPick={onCloudPick}
          onPlane={setPlaneReady}
          onFocus={onFocus}
          onClear={onClearSelection}
        />

        {hasContent && <GraphLegend archive={archive} />}
      </section>
    </>
  );
}
