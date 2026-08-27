import { lazy, Suspense, useCallback, useRef, type KeyboardEvent } from "react";
import { layoutTime, type LayoutMode } from "../../hooks/layout";
import { useElementSize } from "../../hooks/size";
import type { Theme } from "../../hooks/theme";
import { useWebgl } from "../../hooks/webgl";
import { findNextNode, type ArrowKey } from "../../lib/nav";
import type { CameraView } from "../../lib/camera";
import type { GraphData, GraphNode } from "../../types";
import type { CloudData } from "../../lib/cloud";
import type { CloudPaper } from "../../lib/cloud";
import { GraphControls } from "./Controls";
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
  cloudSelected: boolean;
  selected: GraphNode | null;
  onChoose: (node: GraphNode) => void;
  onCloudPick: (paper: CloudPaper) => void;
  onFocus: (nodeId: string) => void;
  onClearSelection: () => void;
  onReset: () => void;
  query: string;
  theme: Theme;
  layout: LayoutMode;
  shareUrl: (camera?: CameraView | null) => string;
  onLayout: (mode: LayoutMode) => void;
  camera: CameraView | null;
};

export function GraphCanvas({
  graph,
  cloud,
  cloudSelected,
  selected,
  onChoose,
  onCloudPick,
  onFocus,
  onClearSelection,
  onReset,
  query,
  theme,
  layout,
  shareUrl,
  onLayout,
  camera,
}: GraphCanvasProps) {
  const { ref: containerRef, width, height } = useElementSize<HTMLElement>();
  const { mode, status, retry } = useWebgl(containerRef);
  const graphRef = useRef<GraphRef["current"]>();
  const fallbackRef = useRef<FallbackRef["current"]>();
  const selectedId = graph.nodes.some((node) => node.id === selected?.id)
    ? (selected?.id ?? "")
    : "";
  const visibleCount =
    graph.nodes.length + (mode === "3d" ? (cloud?.scopes.length ?? 0) : 0);

  const resetView = useCallback(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const duration = layoutTime(Boolean(reduced), 700);
    if (mode === "3d") {
      graphRef.current?.zoomToFit(duration, 72);
    } else {
      fallbackRef.current?.zoomToFit(duration, 72);
    }
  }, [fallbackRef, graphRef, mode]);

  return (
    <>
      <ResultStatus count={visibleCount} label="visible graph node" query={query} />
      <section
        className="graph-wrap"
        ref={containerRef}
        aria-label={`Interactive ${mode === "3d" ? "3D " : ""}research graph`}
        aria-describedby="graph-help"
        tabIndex={0}
        onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
          if (event.target !== event.currentTarget) return;
          if (!event.key.startsWith("Arrow")) return;
          event.preventDefault();
          const projector = graphRef.current;
          const projected = graph.nodes.map((node) => {
            if (!projector || node.x == null || node.y == null || node.z == null) {
              return node;
            }
            const point = projector.graph2ScreenCoords(node.x, node.y, node.z);
            return { ...node, x: point.x, y: point.y };
          });
          const projectedSelection = selected
            ? (projected.find((node) => node.id === selected.id) ?? null)
            : null;
          const next = findNextNode(
            projected,
            projectedSelection,
            event.key as ArrowKey,
          );
          const source = graph.nodes.find((node) => node.id === next?.id);
          if (source) onChoose(source);
        }}
      >
        <GraphHelp mode={mode} selected={selected} />
        <GraphControls
          count={visibleCount}
          mode={mode}
          layout={layout}
          onReset={resetView}
        >
          <GraphTools
            graphRef={graphRef}
            fallbackRef={fallbackRef}
            height={height}
            layout={layout}
            mode={mode}
            nodes={graph.nodes}
            onChoose={onChoose}
            onLayout={onLayout}
            selected={selected}
            selectedId={selectedId}
            shareUrl={shareUrl}
          />
        </GraphControls>
        <WebglStatus status={status} onRetry={retry} />

        {graph.nodes.length === 0 && (
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

        {mode === "3d" && graph.nodes.length > 0 && width > 0 && height > 0 && (
          <Suspense
            fallback={
              <p
                className="graph-loading"
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                Loading 3D space…
              </p>
            }
          >
            <GraphSpace
              graph={graph}
              cloud={cloud}
              cloudSelected={cloudSelected}
              graphRef={graphRef}
              width={width}
              height={height}
              selected={selected}
              theme={theme}
              layout={layout}
              camera={camera}
              onChoose={(node) => {
                onChoose(node);
                containerRef.current?.focus({ preventScroll: true });
              }}
              onCloudPick={onCloudPick}
              onFocus={onFocus}
              onClear={onClearSelection}
            />
          </Suspense>
        )}

        {mode === "2d" && graph.nodes.length > 0 && width > 0 && height > 0 && (
          <Suspense
            fallback={
              <p
                className="graph-loading"
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                Loading compatibility view…
              </p>
            }
          >
            <GraphFallback
              graph={graph}
              graphRef={fallbackRef}
              width={width}
              height={height}
              selected={selected}
              theme={theme}
              layout={layout}
              camera={camera}
              onChoose={(node) => {
                onChoose(node);
                containerRef.current?.focus({ preventScroll: true });
              }}
              onFocus={onFocus}
              onClear={onClearSelection}
            />
          </Suspense>
        )}

        {graph.nodes.length > 0 && <GraphLegend />}
      </section>
    </>
  );
}
