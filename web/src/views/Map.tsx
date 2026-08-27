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
import { PaperSheet, PaperState } from "../components/map/State";
import type { Theme } from "../hooks/theme";
import type { CameraView } from "../lib/camera";
import { resolvePaper } from "../lib/filters";
import { useCloud } from "../hooks/cloud";
import type { CloudPaper } from "../lib/cloud";

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
  onPush: (patch: Partial<AtlasUrlState>) => void;
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
  onPush,
}: MapViewProps) {
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [cloudPaper, setCloudPaper] = useState<CloudPaper | null>(null);
  const kinds = useMemo(() => new Set(url.kinds), [url.kinds]);
  const history = useCloud(kinds.has("paper") && url.layout === "semantic");
  const visibleCloud = url.focus || url.query.trim() ? null : history.data;
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
    if (cloudPaper && !visibleCloud) setCloudPaper(null);
  }, [cloudPaper, visibleCloud]);

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
    setCloudPaper(null);
    onReplace({ selected: node.id });
    if (node.kind !== "paper" && !papersReady) onNeedPapers();
  }

  function chooseNodeId(nodeId: string) {
    const node = allNodes.find((candidate) => candidate.id === nodeId);
    if (!node) return;
    setCloudPaper(null);
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
    onPush({ focus: url.focus === nodeId ? null : nodeId });
  }

  function resetMap() {
    setCloudPaper(null);
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
      <PaperState loading={papersLoading} error={papersError} retry={onRetryPapers} />
      <MapFilters
        atlas={atlas}
        archiveCount={history.manifest?.count}
        kinds={kinds}
        focus={url.focus}
        minFeasibility={url.minFeasibility}
        onToggleKind={toggleKind}
        onMinFeasibilityChange={(value) => onReplace({ minFeasibility: value })}
        onClearFocus={() => onPush({ focus: null })}
      />
      <GraphCanvas
        graph={graph}
        cloud={visibleCloud}
        cloudSelected={Boolean(cloudPaper)}
        selected={selected}
        onChoose={chooseNode}
        onCloudPick={(paper) => {
          setCloudPaper(paper);
          onReplace({ selected: null, focus: null });
        }}
        onFocus={toggleFocus}
        onClearSelection={() => {
          setCloudPaper(null);
          onReplace({ selected: null });
        }}
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
        cloud={cloudPaper}
        hasNodes={graph.nodes.length > 0}
        atlas={atlas}
        focused={url.focus === selected?.id}
        onFocus={toggleFocus}
        onSelectNode={chooseNodeId}
        onClose={() => {
          setCloudPaper(null);
          onReplace({ selected: null });
        }}
        onOpenPaper={setSelectedPaper}
      />
      <PaperSheet paper={selectedPaper} close={() => setSelectedPaper(null)} />
    </main>
  );
}
