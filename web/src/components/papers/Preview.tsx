import type { FullReadingLoadState } from "../../hooks/reading";
import type { Paper } from "../../types";
import { ModalSection } from "../shared/Section";

type PreviewProps = {
  paper: Paper;
  hasReading: boolean;
  isContext: boolean;
  state: FullReadingLoadState;
  retry: () => void;
};

export function PaperPreview({
  paper,
  hasReading,
  isContext,
  state,
  retry,
}: PreviewProps) {
  return (
    <>
      <div className="modal-columns">
        <div>
          <ModalSection title="Problem">
            <p>{paper.reading.problem}</p>
          </ModalSection>
          <ModalSection title="Approach">
            <p>{paper.reading.approach}</p>
          </ModalSection>
          <ModalSection title="Reported evidence">
            <p>{paper.reading.evidence}</p>
          </ModalSection>
        </div>
        <div>
          <ModalSection title="Why it matters">
            <p>{paper.reading.why_it_matters}</p>
          </ModalSection>
          <ModalSection title="Preview limitations">
            <p>{paper.reading.limitations}</p>
          </ModalSection>
        </div>
      </div>
      {!hasReading && (
        <div className="callout compact-callout">
          <div>
            <h2>Evidence boundary</h2>
            {isContext ? (
              <p>
                This collection entry is contextual material, not a research paper. It
                remains visible for provenance but is excluded from paper counts,
                synthesis, and reading-completion requirements.
              </p>
            ) : (
              <p>
                This record has not received a page-anchored full-paper review. Treat
                the summary as routing evidence, not a verified synthesis.
              </p>
            )}
          </div>
        </div>
      )}
      {hasReading && (state.status === "idle" || state.status === "loading") && (
        <div
          className="callout compact-callout reading-load-state"
          role="status"
          aria-live="polite"
        >
          <div>
            <h2>Loading full review</h2>
            <p>Fetching the page-anchored evidence and provenance for this paper.</p>
          </div>
        </div>
      )}
      {hasReading && state.status === "error" && (
        <div className="callout compact-callout reading-load-state error" role="alert">
          <div>
            <h2>Full review unavailable</h2>
            <p>{state.error}</p>
            <button type="button" onClick={retry}>
              Retry full review
            </button>
          </div>
        </div>
      )}
    </>
  );
}
