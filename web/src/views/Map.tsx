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
import { PaperDetailModal } from "../components/papers/Paper";
import { ResultStatus } from "../components/shared/Empty";
import type { Theme } from "../hooks/theme";
import type { CameraView } from "../lib/camera";
import { resolvePaper } from "../lib/filters";
import { useCloud } from "../hooks/cloud";

type MapViewProps = {
  atlas: AtlasRead;
  theme: Theme;
  url: AtlasUrlState;
  shareUrl: (camera?: CameraView | null) => string;
  papersReady: boolean;
  papersLoading: boolean;
  papersError: string | null;
  onNeedPapers: () => void;
  onRetryPapers: () => void;
  onReplace: (patch: Partial<AtlasUrlState>) => void;
};

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
}: MapViewProps) {
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const kinds = useMemo(() => new Set(url.kinds), [url.kinds]);
  const history = useCloud(kinds.has("paper") && url.layout === "semantic");
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

  function toggleKind(kind: GraphNodeKind) {
    const next = new Set(kinds);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    if (kind === "paper" && next.has(kind)) onNeedPapers();
    onReplace({ kinds: ALL_NODE_KINDS.filter((item) => next.has(item)) });
  }

  function chooseNode(node: GraphNode) {
    onReplace({ selected: node.id });
    if (node.kind !== "paper" && !papersReady) onNeedPapers();
  }

  function chooseNodeId(nodeId: string) {
    const node = allNodes.find((candidate) => candidate.id === nodeId);
    if (!node) return;
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
    onReplace({ focus: url.focus === nodeId ? null : nodeId });
  }

  function resetMap() {
    onReplace({
      kinds: [...ALL_NODE_KINDS],
      focus: null,
      minFeasibility: 1,
      selected: null,
      query: "",
      layout: "semantic",
    });
  }

  return (
    <main className="map-layout">
      <ResultStatus
        count={graph.nodes.length + (history.data?.scopes.length ?? 0)}
        label="visible graph node"
        query={url.query}
      />
      {(papersLoading || papersError) && (
        <aside
          className="paper-state"
          role={papersError ? "alert" : "status"}
          aria-live="polite"
          aria-atomic="true"
          aria-busy={papersLoading}
        >
          <span>
            {papersError
              ? `Paper index unavailable: ${papersError}`
              : "Loading papers…"}
          </span>
          {papersError && (
            <button type="button" onClick={onRetryPapers}>
              Retry papers
            </button>
          )}
        </aside>
      )}
      <MapFilters
        atlas={atlas}
        archiveCount={history.manifest?.count}
        kinds={kinds}
        focus={url.focus}
        minFeasibility={url.minFeasibility}
        onToggleKind={toggleKind}
        onMinFeasibilityChange={(value) => onReplace({ minFeasibility: value })}
        onClearFocus={() => onReplace({ focus: null })}
      />
      <GraphCanvas
        graph={graph}
        cloud={history.data}
        selected={selected}
        onChoose={chooseNode}
        onFocus={toggleFocus}
        onClearSelection={() => onReplace({ selected: null })}
        onReset={resetMap}
        query={url.query}
        theme={theme}
        layout={url.layout}
        camera={url.camera}
        shareUrl={shareUrl}
        onLayout={(layout) => onReplace({ layout })}
      />
      <PanelResize />
      <Inspector
        node={selected}
        hasNodes={graph.nodes.length > 0}
        atlas={atlas}
        focused={url.focus === selected?.id}
        onFocus={toggleFocus}
        onSelectNode={chooseNodeId}
        onClose={() => onReplace({ selected: null })}
        onOpenPaper={setSelectedPaper}
      />
      {selectedPaper && (
        <PaperDetailModal
          paper={selectedPaper}
          close={() => {
            setSelectedPaper(null);
          }}
        />
      )}
    </main>
  );
}
