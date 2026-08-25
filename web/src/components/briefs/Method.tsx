import type { Brief } from "../../types";
import { BulletList } from "../shared/Bullets";
import { ModalSection } from "../shared/Section";

type MethodProps = {
  detail: Brief;
};

export function MethodColumn({ detail }: MethodProps) {
  return (
    <div>
      <ModalSection title="Research question">
        <p>{detail.research_question}</p>
        {detail.subquestions && <BulletList items={detail.subquestions} />}
      </ModalSection>
      <ModalSection title="Motivation">
        <p>{detail.motivation}</p>
      </ModalSection>
      {detail.non_claims && (
        <ModalSection title="What this project does not claim">
          <BulletList items={detail.non_claims} />
        </ModalSection>
      )}
      {detail.method && (
        <ModalSection title="Method">
          <ol>
            {detail.method.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </ModalSection>
      )}
      {detail.route_dictionary_protocol && (
        <ModalSection title="Frozen route dictionary">
          <div className="protocol-card">
            <h4>Shared axes</h4>
            <BulletList items={detail.route_dictionary_protocol.shared_axes} />
            <h4>Markov-family routes</h4>
            <BulletList items={detail.route_dictionary_protocol.markov_family} />
            <h4>Regression-family routes</h4>
            <BulletList items={detail.route_dictionary_protocol.regression_family} />
            <h4>Freeze boundary</h4>
            <p>{detail.route_dictionary_protocol.freeze_boundary}</p>
            <h4>Invalidation rules</h4>
            <BulletList items={detail.route_dictionary_protocol.invalidation_rules} />
          </div>
        </ModalSection>
      )}
      {detail.generation_routes && (
        <ModalSection title="Environment generation routes">
          <div className="route-grid">
            {detail.generation_routes.map((route) => (
              <article key={route.route}>
                <h4>{route.route}</h4>
                <p>{route.mechanism}</p>
                <small>
                  <b>Examples:</b> {route.examples}
                </small>
                <small>
                  <b>Best when:</b> {route.best_when}
                </small>
              </article>
            ))}
          </div>
        </ModalSection>
      )}
      {detail.core_design && (
        <ModalSection title="Core design">
          <h4>Unit of search</h4>
          <p>{detail.core_design.unit_of_search}</p>
          <h4>Generator</h4>
          <p>{detail.core_design.generator}</p>
          <h4>Fitness</h4>
          <BulletList items={detail.core_design.fitness} />
          <h4>Selection</h4>
          <p>{detail.core_design.selection}</p>
          <h4>Critical control</h4>
          <p>{detail.core_design.critical_control}</p>
        </ModalSection>
      )}
      {detail.what_counts_as_learning_signal && (
        <ModalSection title="What counts as learning signal">
          <p>{detail.what_counts_as_learning_signal.answer}</p>
          <div className="funnel evidence-hierarchy">
            {detail.what_counts_as_learning_signal.evidence_hierarchy.map((level) => (
              <div key={level.level}>
                <b>{level.level}</b>
                <span>
                  <strong>{level.name}</strong>
                  <p>{level.evidence}</p>
                  <small>Does not show: {level.does_not_show}</small>
                </span>
              </div>
            ))}
          </div>
          <h4>Recommended statistics</h4>
          <BulletList
            items={detail.what_counts_as_learning_signal.recommended_statistics}
          />
        </ModalSection>
      )}
      {detail.validation_funnel && (
        <ModalSection title="Validation funnel">
          <div className="funnel">
            {detail.validation_funnel.map((stage, index) => (
              <div key={stage.stage}>
                <b>{index + 1}</b>
                <span>
                  <strong>{stage.stage}</strong>
                  <small>{stage.cost} cost</small>
                  <p>{stage.gate}</p>
                </span>
              </div>
            ))}
          </div>
        </ModalSection>
      )}
      <ModalSection title="Evaluation">
        <BulletList items={detail.evaluation} />
      </ModalSection>
    </div>
  );
}
