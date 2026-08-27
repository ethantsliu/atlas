import { ChevronRight, CircleDot, X } from "lucide-react";
import type { CloudPaper } from "../../lib/cloud";

type CloudProps = {
  paper: CloudPaper;
  focused: boolean;
  ready: boolean;
  loading: boolean;
  error: string | null;
  onFocus: () => void;
  onClose: () => void;
};

export function CloudDetail({
  paper,
  focused,
  ready,
  loading,
  error,
  onFocus,
  onClose,
}: CloudProps) {
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
      <span className="type-pill paper">Paper</span>
      <h2 id="map-inspector-title">{paper.title}</h2>
      <div className="confidence">
        <span>Published</span>
        <b>
          <time dateTime={paper.published}>{paper.published.slice(0, 10)}</time>
        </b>
      </div>
      <button
        className="focus-button"
        type="button"
        aria-pressed={focused}
        disabled={!ready}
        onClick={onFocus}
      >
        <CircleDot size={15} />
        {focused ? "Unisolate connections" : "Isolate connections"}
      </button>
      {focused && (
        <p
          className="cloud-relation"
          role={error ? "alert" : "status"}
          aria-live={error ? "assertive" : "polite"}
        >
          {loading
            ? "Loading exact semantic anchors…"
            : (error ??
              "Exact MiniLM cosine anchors in the pinned embedding space; not citations.")}
        </p>
      )}
      <a
        className="focus-button cloud-source"
        href={paper.url}
        target="_blank"
        rel="noreferrer"
      >
        View on arXiv
        <ChevronRight size={15} />
      </a>
    </aside>
  );
}
