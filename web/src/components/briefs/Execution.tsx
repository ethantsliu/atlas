import { labelOf } from "../../lib/text";
import type { Brief, Idea } from "../../types";
import { BulletList } from "../shared/Bullets";
import { ModalSection } from "../shared/Section";
import { ExperimentPlanSection } from "./Plan";

type ExecutionProps = {
  detail: Brief;
  idea: Idea;
};

export function ExecutionColumn({ detail, idea }: ExecutionProps) {
  const humanDecision =
    detail.human_in_the_loop?.answer ?? detail.human_in_the_loop?.short_answer;
  const humanPolicy =
    detail.human_in_the_loop?.policy ?? detail.human_in_the_loop?.routing_policy;
  const scalingDecision =
    detail.scaling_claim_protocol?.answer ??
    detail.scaling_claim_protocol?.short_answer;

  return (
    <div>
      <ModalSection title="Feasibility rationale">
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
        <p className="rubric-version">Feasibility rubric {idea.feasibility.version}</p>
        {idea.feasibility.assumptions.length > 0 && (
          <>
            <h4>Scoring assumptions</h4>
            <BulletList items={idea.feasibility.assumptions} />
          </>
        )}
      </ModalSection>
      {detail.human_in_the_loop && (
        <ModalSection title="Human in the loop">
          {humanDecision && (
            <p>
              <b>Decision:</b> {humanDecision}
            </p>
          )}
          {detail.human_in_the_loop.humans_not_needed_for && (
            <>
              <h4>Automation is enough for</h4>
              <BulletList items={detail.human_in_the_loop.humans_not_needed_for} />
            </>
          )}
          {detail.human_in_the_loop.humans_needed_for && (
            <>
              <h4>Human judgment is needed for</h4>
              <BulletList items={detail.human_in_the_loop.humans_needed_for} />
            </>
          )}
          {humanPolicy && <p>{humanPolicy}</p>}
          <p>{detail.human_in_the_loop.measurement}</p>
        </ModalSection>
      )}
      {detail.scaling_claim_protocol && (
        <ModalSection title="Scaling claim protocol">
          {scalingDecision && (
            <p>
              <b>Decision:</b> {scalingDecision}
            </p>
          )}
          {detail.scaling_claim_protocol.why_small_models_fail && (
            <>
              <h4>Why small-model evidence can fail</h4>
              <BulletList items={detail.scaling_claim_protocol.why_small_models_fail} />
            </>
          )}
          {detail.scaling_claim_protocol.minimum_design && (
            <p>{detail.scaling_claim_protocol.minimum_design}</p>
          )}
          {detail.scaling_claim_protocol.prospective_design && (
            <>
              <h4>Prospective design</h4>
              <BulletList items={detail.scaling_claim_protocol.prospective_design} />
            </>
          )}
          <h4>Evidence required</h4>
          <BulletList items={detail.scaling_claim_protocol.supporting_evidence} />
          <h4>Claim blockers</h4>
          <BulletList items={detail.scaling_claim_protocol.claim_blockers} />
          {detail.scaling_claim_protocol.claim_language && (
            <p className="novelty">
              <b>Claim language:</b> {detail.scaling_claim_protocol.claim_language}
            </p>
          )}
        </ModalSection>
      )}
      {detail.experiment && (
        <ExperimentPlanSection
          experiment={detail.experiment}
          falsifiers={detail.falsifiers}
        />
      )}
      {detail.milestones && (
        <ModalSection title="Milestones and pass conditions">
          <div className="milestone-list">
            {detail.milestones.map((milestone, index) => (
              <article key={milestone.name}>
                <b>{index + 1}</b>
                <div>
                  <h4>{milestone.name}</h4>
                  <p>{milestone.deliverable}</p>
                  <small>
                    <strong>Pass:</strong> {milestone.pass_condition}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </ModalSection>
      )}
      <ModalSection title="Risks">
        <BulletList items={detail.risks} />
      </ModalSection>
      <ModalSection title="First week">
        <ol>
          {detail.first_week.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      </ModalSection>
    </div>
  );
}
