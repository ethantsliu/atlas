import { ChevronRight } from "lucide-react";
import {
  findParentProgram,
  ideaBasis,
  ideaRole,
  workPackagesFor,
} from "../../lib/portfolio";
import { labelOf } from "../../lib/text";
import type { Idea } from "../../types";
import type { AtlasRead } from "../../lib/payload";

type IdeaProps = {
  idea: Idea;
  atlas: AtlasRead;
  onSelectNode: (id: string) => void;
};

export function IdeaDetails({ idea, atlas, onSelectNode }: IdeaProps) {
  const role = ideaRole(idea);
  const parent = findParentProgram(idea, atlas.ideas);
  const workPackages = role === "program" ? workPackagesFor(idea, atlas.ideas) : [];
  return (
    <>
      <p className="idea-basis">{ideaBasis(idea)}</p>
      {parent && (
        <div className="inspector-program-context">
          <span>Work package within</span>
          <button type="button" onClick={() => onSelectNode(parent.id)}>
            {parent.brief.title}
            <ChevronRight size={13} />
          </button>
        </div>
      )}
      {workPackages.length > 0 && (
        <div className="inspector-program-context">
          <span>
            {workPackages.length} testable{" "}
            {workPackages.length === 1 ? "work package" : "work packages"}
          </span>
          {workPackages.map((workPackage) => (
            <button
              type="button"
              onClick={() => onSelectNode(workPackage.id)}
              key={workPackage.id}
            >
              {workPackage.brief.title}
              <ChevronRight size={13} />
            </button>
          ))}
        </div>
      )}
      <div className="feasibility-score">
        <b>{idea.feasibility.score.toFixed(1)}</b>
        <span>
          {idea.feasibility.screening_estimate
            ? "Screening estimate"
            : role === "work-package"
              ? "Module feasibility"
              : role === "program"
                ? "Program feasibility"
                : "Feasibility"}
          <br />
          <em>{idea.feasibility.band}</em>
        </span>
      </div>
      <p className="thesis">{idea.brief.thesis}</p>
      <div className="confidence">
        <span>Connection confidence</span>
        <b>{Math.round(idea.brief.confidence * 100)}%</b>
      </div>
      <h3>Feasibility factors</h3>
      <div className="factor-list">
        {idea.feasibility.factors.map((factor) => (
          <div key={factor.id}>
            <span>{labelOf(factor.id)}</span>
            <b>
              {factor.score.toFixed(1)} / {factor.max.toFixed(1)}
            </b>
            <small>{factor.rationale}</small>
          </div>
        ))}
      </div>
      <h3>Research question</h3>
      <p>{idea.brief.research_question}</p>
      <h3>First week</h3>
      <ol>
        {idea.brief.first_week.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ol>
    </>
  );
}
