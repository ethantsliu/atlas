import { ChevronRight, X } from "lucide-react";
import { useDialog } from "../../hooks/dialog";
import { findPaperIds } from "../../lib/filters";
import {
  findParentProgram,
  ideaBasis,
  ideaRole,
  ideaStage,
  workPackagesFor,
} from "../../lib/portfolio";
import type { Atlas, Idea, Paper } from "../../types";
import { DialogPortal } from "../shared/Portal";
import { EvidenceSections } from "./Evidence";
import { ExecutionColumn } from "./Execution";
import { MethodColumn } from "./Method";

type BriefModalProps = {
  idea: Idea;
  atlas: Atlas;
  close: () => void;
  onOpenIdea: (idea: Idea) => void;
  onOpenPaper: (paper: Paper) => void;
};

export function BriefModal({
  idea,
  atlas,
  close,
  onOpenIdea,
  onOpenPaper,
}: BriefModalProps) {
  const dialogRef = useDialog(close, idea.id);
  const detail = idea.brief;
  const papers = findPaperIds(atlas.papers, detail.paper_ids);
  const role = ideaRole(idea);
  const parentProgram = findParentProgram(idea, atlas.ideas);
  const workPackages = role === "program" ? workPackagesFor(idea, atlas.ideas) : [];

  return (
    <DialogPortal>
      <div
        className="modal-backdrop"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <section
          ref={dialogRef}
          className="brief-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="brief-modal-title"
          tabIndex={-1}
        >
          <header>
            <div>
              <span className="type-pill idea">Idea</span>
              {role !== "standalone" && (
                <span className="type-pill portfolio-role">{role}</span>
              )}
              <span className="type-pill brief-status">{ideaStage(idea)}</span>
              <h1 id="brief-modal-title">{detail.title}</h1>
            </div>
            <button onClick={close} aria-label="Close research idea">
              <X />
            </button>
          </header>
          {parentProgram && (
            <aside className="portfolio-context" aria-label="Parent research program">
              <span>Work package within</span>
              <button type="button" onClick={() => onOpenIdea(parentProgram)}>
                {parentProgram.brief.title}
                <ChevronRight size={14} />
              </button>
            </aside>
          )}
          {workPackages.length > 0 && (
            <aside className="portfolio-context" aria-label="Program work packages">
              <span>Testable work packages</span>
              <div>
                {workPackages.map((workPackage) => (
                  <button
                    type="button"
                    onClick={() => onOpenIdea(workPackage)}
                    key={workPackage.id}
                  >
                    {workPackage.brief.title}
                    <ChevronRight size={14} />
                  </button>
                ))}
              </div>
            </aside>
          )}
          <div className="modal-score">
            <b>{idea.feasibility.score.toFixed(1)}</b>
            <span>
              {idea.feasibility.screening_estimate
                ? "Preliminary feasibility"
                : role === "work-package"
                  ? "Module feasibility"
                  : role === "program"
                    ? "Program feasibility"
                    : "Feasibility"}{" "}
              · {idea.feasibility.band}
            </span>
            <em>{Math.round(detail.confidence * 100)}% evidence connection</em>
          </div>
          <p className="modal-thesis">{detail.thesis}</p>
          <aside className="brief-evidence-basis" aria-label="Evidence basis">
            <b>Evidence basis</b>
            <span>
              {ideaBasis(idea)} {detail.evidence_note}
            </span>
          </aside>
          <div className="modal-columns">
            <MethodColumn detail={detail} />
            <ExecutionColumn detail={detail} idea={idea} />
          </div>
          <EvidenceSections detail={detail} papers={papers} onOpenPaper={onOpenPaper} />
        </section>
      </div>
    </DialogPortal>
  );
}
