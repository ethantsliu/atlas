import { ChevronRight, X } from "lucide-react";
import type { CloudPaper } from "../../lib/cloud";

type CloudProps = {
  paper: CloudPaper;
  onClose: () => void;
};

export function CloudDetail({ paper, onClose }: CloudProps) {
  return (
    <aside
      id="map-inspector"
      className="inspector panel"
      aria-label="Node inspector"
      tabIndex={-1}
    >
      <button className="icon-close" onClick={onClose} aria-label="Close inspector">
        <X size={16} />
      </button>
      <span className="type-pill paper">Paper</span>
      <h2>{paper.title}</h2>
      <div className="confidence">
        <span>Published</span>
        <b>
          <time dateTime={paper.published}>{paper.published.slice(0, 10)}</time>
        </b>
      </div>
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
