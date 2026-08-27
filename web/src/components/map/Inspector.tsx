import { useMemo } from "react";
import { ChevronRight, CircleDot, Sparkles, X } from "lucide-react";
import { findNodePapers } from "../../lib/filters";
import { createGraphNodes } from "../../lib/graph";
import { ideaStage } from "../../lib/portfolio";
import { labelOf } from "../../lib/text";
import type { GraphNode, Paper } from "../../types";
import type { AtlasRead } from "../../lib/payload";
import type { CloudPaper } from "../../lib/cloud";
import { IdeaDetails } from "./Idea";
import { CloudDetail } from "./Cloud";

type InspectorProps = {
  node: GraphNode | null;
  cloud: CloudPaper | null;
  hasNodes: boolean;
  atlas: AtlasRead;
  focused: boolean;
  cloudFocused: boolean;
  cloudReady: boolean;
  cloudLoading: boolean;
  cloudError: string | null;
  onFocus: (id: string) => void;
  onCloudFocus: () => void;
  onSelectNode: (id: string) => void;
  onClose: () => void;
  onOpenPaper: (paper: Paper) => void;
};

export function Inspector({
  node,
  cloud,
  hasNodes,
  atlas,
  focused,
  cloudFocused,
  cloudReady,
  cloudLoading,
  cloudError,
  onFocus,
  onCloudFocus,
  onSelectNode,
  onClose,
  onOpenPaper,
}: InspectorProps) {
  const nodeMap = useMemo(
    () => new Map(createGraphNodes(atlas, 1).map((item) => [item.id, item])),
    [atlas],
  );
  if (cloud) {
    return (
      <CloudDetail
        paper={cloud}
        focused={cloudFocused}
        ready={cloudReady}
        loading={cloudLoading}
        error={cloudError}
        onFocus={onCloudFocus}
        onClose={onClose}
      />
    );
  }
  if (!node) {
    return (
      <aside
        id="map-inspector"
        className="inspector panel empty"
        aria-labelledby="map-inspector-title"
        tabIndex={-1}
      >
        <Sparkles size={28} />
        <h2 id="map-inspector-title">
          {hasNodes ? "Follow a promising edge" : "No node to inspect"}
        </h2>
        {hasNodes ? (
          <p>
            Select a node to see its evidence, related papers, and next actions.
            Right-click a node to isolate its neighborhood.
          </p>
        ) : (
          <p>Reset the map to restore searchable research areas and ideas.</p>
        )}
      </aside>
    );
  }

  const papers = findNodePapers(node, atlas.papers);
  const idea = node.kind === "idea" ? node.payload : null;
  const paper = node.kind === "paper" ? node.payload : null;
  const neighbors = (atlas.layout?.neighbors[node.id] ?? [])
    .map((entry) => ({ ...entry, node: nodeMap.get(entry.id) }))
    .filter((entry): entry is typeof entry & { node: GraphNode } => Boolean(entry.node))
    .slice(0, 6);

  return (
    <aside
      id="map-inspector"
      className="inspector panel"
      aria-labelledby="map-inspector-title"
      tabIndex={-1}
    >
      <button className="icon-close" onClick={onClose} aria-label="Close inspector">
        <X size={16} />
      </button>
      <span className={`type-pill ${node.kind}`}>{labelOf(node.kind)}</span>
      {idea && <span className="type-pill brief-status">{ideaStage(idea)}</span>}
      <h2 id="map-inspector-title">{node.label}</h2>
      {node.count != null && (
        <div className="big-stat">
          {node.count.toLocaleString()} <span>routed papers</span>
        </div>
      )}
      <button
        className="focus-button"
        aria-pressed={focused}
        onClick={() => onFocus(node.id)}
      >
        <CircleDot size={15} />
        {focused ? "Unisolate connections" : "Isolate connections"}
      </button>
      {idea && <IdeaDetails idea={idea} atlas={atlas} onSelectNode={onSelectNode} />}
      {paper && (
        <>
          <p className="thesis">{paper.reading.problem}</p>
          <div className="confidence">
            <span>
              {paper.record_kind === "non_paper_context"
                ? "Record type"
                : "Evidence depth"}
            </span>
            <b>
              {paper.record_kind === "non_paper_context"
                ? "Paper"
                : labelOf(paper.reading_depth)}
            </b>
          </div>
          <p>{paper.reading.approach}</p>
          <button
            className="focus-button"
            type="button"
            onClick={() => onOpenPaper(paper)}
          >
            Open paper
            <ChevronRight size={15} />
          </button>
        </>
      )}
      {neighbors.length > 0 && (
        <section className="nearby" aria-labelledby="nearby-heading">
          <h3 id="nearby-heading">Semantically nearby</h3>
          <p>
            Exact cosine neighbors in the pinned embedding space; not a citation or
            evidence link.
          </p>
          <ol>
            {neighbors.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  aria-label={`${labelOf(entry.node.kind)} ${entry.node.label}`}
                  onClick={() => {
                    onSelectNode(entry.node.id);
                  }}
                >
                  <span>{labelOf(entry.node.kind)}</span>
                  <b>{entry.node.label}</b>
                  <small>cosine {entry.score.toFixed(2)}</small>
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}
      {papers.length > 0 && (
        <>
          <h3>
            Collection evidence <small>{papers.length}</small>
          </h3>
          <div className="paper-stack">
            {papers.slice(0, 6).map((paper) => (
              <button
                type="button"
                onClick={() => onSelectNode(paper.id)}
                key={paper.id}
              >
                <span>
                  {paper.record_kind === "non_paper_context"
                    ? "paper"
                    : paper.reading_depth}
                </span>
                {paper.title}
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
