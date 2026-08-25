import { ChevronRight } from "lucide-react";
import type { Brief, Paper } from "../../types";
import { ModalSection } from "../shared/Section";
import { Landscape } from "./Landscape";

type EvidenceProps = {
  detail: Brief;
  papers: Paper[];
  onOpenPaper: (paper: Paper) => void;
};

export function EvidenceSections({ detail, papers, onOpenPaper }: EvidenceProps) {
  return (
    <>
      {detail.competitive_landscape && (
        <ModalSection title="Related work">
          <Landscape competitors={detail.competitive_landscape} />
          {detail.novelty_assessment && (
            <p className="novelty">
              <b>Novelty assessment:</b> {detail.novelty_assessment}
            </p>
          )}
        </ModalSection>
      )}
      {detail.reading_roles && (
        <ModalSection title="Collection reading roles">
          <div className="reading-role-grid">
            {detail.reading_roles.map((readingRole) => {
              const paper = papers.find(
                (candidate) =>
                  candidate.id === readingRole.paper_id ||
                  candidate.stable_id === readingRole.paper_id,
              );
              return (
                <article key={readingRole.paper_id}>
                  <span>{readingRole.role}</span>
                  <b>{paper?.title ?? readingRole.paper_id}</b>
                  <p>{readingRole.use}</p>
                </article>
              );
            })}
          </div>
        </ModalSection>
      )}
      {papers.length > 0 && (
        <ModalSection title="Collection evidence">
          <div className="paper-stack">
            {papers.map((paper) => (
              <button type="button" onClick={() => onOpenPaper(paper)} key={paper.id}>
                <span>
                  {paper.record_kind === "non_paper_context"
                    ? "context"
                    : paper.reading_depth}
                </span>
                {paper.title}
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </ModalSection>
      )}
    </>
  );
}
