import { useEffect, useMemo, useState } from "react";
import { ALL_NODE_KINDS, buildGraph, createGraphNodes } from "../lib/graph";
import type { GraphNode, GraphNodeKind, Paper } from "../types";
import type { AtlasRead } from "../lib/payload";
import { useGraph } from "../hooks/graph";
import type { AtlasUrlState } from "../hooks/url";
import { GraphCanvas } from "../components/map/Graph";
import { Inspector } from "../components/map/Inspector";
import { PanelResize } from "../components/map/Panel";
import { MapFilters } from "../components/map/Filters";
import { CloudState, PaperSheet, PaperState } from "../components/map/State";
import type { Theme } from "../hooks/theme";
import type { CameraView } from "../lib/camera";
import { resolvePaper } from "../lib/filters";
import { useCloud, type CloudLoad } from "../hooks/cloud";
import { useFocus } from "../hooks/focus";
import type { RenderMode } from "../hooks/webgl";
import "../hit.css";

type MapViewProps = {
  atlas: AtlasRead;
  theme: Theme;
  url: AtlasUrlState;
  shareUrl: (camera?: CameraView | null, render?: RenderMode) => string;
  papersReady: boolean;
  papersLoading: boolean;
  papersError: string | null;
  onNeedPapers: () => void;
  onRetryPapers: () => void;
  onReplace: (patch: Partial<AtlasUrlState>) => void;
  onPush: (patch: Partial<AtlasUrlState>) => void;
};

const RESET_MAP: Partial<AtlasUrlState> = {
  kinds: [...ALL_NODE_KINDS],
  focus: null,
  minFeasibility: 1,
  selected: null,
  query: "",
  layout: "semantic",
};

function showInspector(): void {
  if (!window.matchMedia?.("(max-width: 1100px)").matches) return;
  window.requestAnimationFrame(() => {
    const inspector = document.getElementById("map-inspector");
    if (!inspector) return;
    inspector.focus({ preventScroll: true });
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    inspector.scrollIntoView({
      behavior: reduced ? "auto" : "smooth",
      block: "start",
    });
  });
}

function mapReady(
  hasPapers: boolean,
  cloudEnabled: boolean,
  papersReady: boolean,
  papersError: string | null,
  history: CloudLoad,
) {
  const papersDone = !hasPapers || papersReady || Boolean(papersError);
  const cloudDone =
    !hasPapers ||
    !cloudEnabled ||
    (!history.loading && Boolean(history.data || history.error));
  return {
    camera:
      papersDone &&
      (!hasPapers || !cloudEnabled || Boolean(history.data?.loaded || history.error)),
    view: papersDone && cloudDone,
  };
}

function useSelection(
  atlas: AtlasRead,
  graph: ReturnType<typeof useGraph>,
  papersReady: boolean,
  url: AtlasUrlState,
  onReplace: (patch: Partial<AtlasUrlState>) => void,
) {
  const selected =
    graph.nodes.find((candidate) => candidate.id === url.selected) ?? null;

  useEffect(() => {
    if (!papersReady || !url.selected || selected) return;
    const paper = resolvePaper(atlas.papers, url.selected);
    if (paper) onReplace({ selected: paper.id });
  }, [atlas.papers, onReplace, papersReady, selected, url.selected]);

  useEffect(() => {
    const visibleIds = new Set(graph.nodes.map((node) => node.id));
    const waitingSelection = !papersReady && Boolean(url.selected);
    const hiddenPaper = Boolean(resolvePaper(atlas.papers, url.selected));
    const waitingFocus = !papersReady && Boolean(url.focus?.startsWith("paper-"));
    if (
      url.selected &&
      !visibleIds.has(url.selected) &&
      !waitingSelection &&
      !hiddenPaper
    ) {
      onReplace({ selected: null });
    }
    if (url.focus && !visibleIds.has(url.focus) && !waitingFocus) {
      onReplace({ focus: null });
    }
  }, [atlas.papers, graph.nodes, onReplace, papersReady, url.focus, url.selected]);

  return selected;
}

export function MapView({
  atlas,
  theme,
  url,
  shareUrl,
  papersReady,
  papersLoading,
  papersError,
  onNeedPapers,
  onRetryPapers,
  onReplace,
  onPush,
}: MapViewProps) {
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [activeMode, setActiveMode] = useState<RenderMode>("2d");
  const kinds = useMemo(() => new Set(url.kinds), [url.kinds]);
  const cloudEnabled =
    activeMode === "3d" && kinds.has("paper") && url.layout === "semantic";
  const history = useCloud(cloudEnabled);
  const ready = mapReady(
    kinds.has("paper"),
    cloudEnabled,
    papersReady,
    papersError,
    history,
  );
  const cloud = useFocus(atlas, history, Boolean(url.focus || url.query.trim()));
  const nextGraph = useMemo(
    () =>
      buildGraph(atlas, {
        kinds,
        focus: url.focus,
        selected: url.selected,
        query: url.query,
        minFeasibility: url.minFeasibility,
      }),
    [atlas, kinds, url.focus, url.minFeasibility, url.query, url.selected],
  );
  const graph = useGraph(nextGraph);
  const allNodes = useMemo(() => createGraphNodes(atlas, 1), [atlas]);
  const selected = useSelection(atlas, graph, papersReady, url, onReplace);

  useEffect(() => {
    if (cloud.pick || selected) showInspector();
  }, [cloud.pick, selected]);

  function toggleKind(kind: GraphNodeKind) {
    const next = new Set(kinds);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    if (kind === "paper" && next.has(kind)) onNeedPapers();
    onReplace({ kinds: ALL_NODE_KINDS.filter((item) => next.has(item)) });
  }

  function chooseNode(node: GraphNode) {
    cloud.clear();
    onReplace({ selected: node.id });
    if (node.kind !== "paper" && !papersReady) onNeedPapers();
  }

  function chooseNodeId(nodeId: string) {
    const node = allNodes.find((candidate) => candidate.id === nodeId);
    if (!node) return;
    cloud.clear();
    const nextKinds = new Set(kinds);
    if (node.kind !== "paper") nextKinds.add(node.kind);
    onReplace({
      kinds: ALL_NODE_KINDS.filter((kind) => nextKinds.has(kind)),
      focus: null,
      query: "",
      minFeasibility: node.kind === "idea" ? 1 : url.minFeasibility,
      selected: node.id,
    });
  }

  function toggleFocus(nodeId: string) {
    cloud.clear();
    onPush({ focus: url.focus === nodeId ? null : nodeId });
  }

  function togglePanel(nodeId: string) {
    toggleFocus(url.focus ?? nodeId);
  }

  function resetMap() {
    cloud.clear();
    onReplace(RESET_MAP);
  }

  return (
    <main className="map-layout">
      <PaperState loading={papersLoading} error={papersError} retry={onRetryPapers} />
      <CloudState
        loading={!papersLoading && !papersError && history.loading}
        error={!papersLoading && !papersError ? history.error : null}
        retry={history.retry}
      />
      <MapFilters
        atlas={atlas}
        archiveCount={activeMode === "3d" ? history.manifest?.count : undefined}
        kinds={kinds}
        focus={url.focus}
        minFeasibility={url.minFeasibility}
        onToggleKind={toggleKind}
        onMinFeasibilityChange={(value) => onReplace({ minFeasibility: value })}
        onClearFocus={() => onPush({ focus: null })}
      />
      <GraphCanvas
        graph={cloud.focused ? (cloud.graph ?? { nodes: [], links: [] }) : graph}
        cloud={cloud.data}
        cloudHidden={cloud.hidden}
        cloudLabel={cloud.pick?.paper.title ?? null}
        cloudSelected={Boolean(cloud.pick)}
        cloudMark={cloud.mark}
        selected={selected}
        onChoose={chooseNode}
        onCloudPick={(pick) => {
          cloud.choose(pick);
          onReplace({ selected: null, focus: null });
        }}
        onFocus={toggleFocus}
        onClearSelection={() => {
          cloud.clear();
          onReplace({ selected: null });
        }}
        onReset={resetMap}
        query={url.query}
        theme={theme}
        layout={url.layout}
        render={url.render}
        camera={url.camera}
        cameraReady={ready.camera}
        viewReady={ready.view}
        shareUrl={shareUrl}
        onLayout={(layout) => onReplace({ layout })}
        onRender={(render) => onPush({ render })}
        onMode={setActiveMode}
      />
      <PanelResize />
      <Inspector
        node={selected}
        cloud={cloud.pick?.paper ?? null}
        hasNodes={graph.nodes.length > 0}
        atlas={atlas}
        focused={Boolean(url.focus)}
        cloudFocused={cloud.focused}
        cloudReady={cloud.ready}
        cloudLoading={cloud.loading}
        cloudError={cloud.error}
        onFocus={togglePanel}
        onCloudFocus={cloud.toggle}
        onSelectNode={chooseNodeId}
        onClose={() => {
          cloud.clear();
          onReplace({ selected: null });
        }}
        onOpenPaper={setSelectedPaper}
      />
      <PaperSheet paper={selectedPaper} close={() => setSelectedPaper(null)} />
    </main>
  );
}
