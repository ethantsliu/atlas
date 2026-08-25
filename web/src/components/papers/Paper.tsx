import { ExternalLink, X } from "lucide-react";
import { useDialog } from "../../hooks/dialog";
import { useFullReading } from "../../hooks/reading";
import { labelOf } from "../../lib/text";
import type { Paper } from "../../types";
import { DialogPortal } from "../shared/Portal";
import { ReadingCompetition } from "./Competition";
import { PaperPreview } from "./Preview";
import { ReadingEvidence } from "./Source";
import { ReadingSynthesis } from "./Synthesis";

type PaperDetailModalProps = {
  paper: Paper;
  close: () => void;
};

export function PaperDetailModal({ paper, close }: PaperDetailModalProps) {
  const dialogRef = useDialog(close);
  const { state, retry } = useFullReading(paper);
  const reading = state.status === "loaded" ? state.reading : null;
  const hasReading = Boolean(paper.full_reading_path);
  const isContext = paper.record_kind === "non_paper_context";
  const showCollectionLink = paper.collection_url !== paper.url;
  const evidenceLabel = isContext
    ? "Context"
    : hasReading
      ? "Full"
      : labelOf(paper.reading_depth);
  const evidenceDescription = isContext
    ? "Curator context · excluded from the paper corpus"
    : paper.reading_depth === "verified"
      ? "Page-anchored reading · independently checked"
      : hasReading
        ? "Page-anchored full-paper reading"
        : `Collection preview · ${labelOf(paper.reading_depth)} evidence`;

  return (
    <DialogPortal>
      <div
        className="modal-backdrop paper-modal-backdrop"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <section
          ref={dialogRef}
          className="brief-modal paper-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="paper-modal-title"
          tabIndex={-1}
        >
          <header>
            <div>
              <span className="type-pill topic">
                {isContext ? "context" : paper.reading_depth}
              </span>
              <h1 id="paper-modal-title">{paper.title}</h1>
              <p className="paper-byline">
                {paper.authors?.join(", ") || paper.source}
              </p>
            </div>
            <button onClick={close} aria-label="Close paper details">
              <X />
            </button>
          </header>
          <div className="modal-score paper-score">
            <b>{evidenceLabel}</b>
            <span>{evidenceDescription}</span>
            {reading && (
              <em>{Math.round(reading.confidence * 100)}% review confidence</em>
            )}
            <a href={paper.url} target="_blank" rel="noreferrer">
              {isContext ? "Context source" : "Source"} <ExternalLink size={13} />
            </a>
            {showCollectionLink && (
              <a href={paper.collection_url} target="_blank" rel="noreferrer">
                Collection link <ExternalLink size={13} />
              </a>
            )}
          </div>
          <PaperPreview
            paper={paper}
            hasReading={hasReading}
            isContext={isContext}
            state={state}
            retry={retry}
          />
          {reading && (
            <>
              <ReadingEvidence reading={reading} />
              <ReadingSynthesis reading={reading} />
              <ReadingCompetition reading={reading} />
            </>
          )}
        </section>
      </div>
    </DialogPortal>
  );
}
