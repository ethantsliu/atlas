import type { ExperimentPlan } from "../../types";
import { BulletList } from "../shared/Bullets";
import { ModalSection } from "../shared/Section";

type ExperimentPlanSectionProps = {
  experiment: ExperimentPlan;
  falsifiers?: string[];
};

export function ExperimentPlanSection({
  experiment,
  falsifiers,
}: ExperimentPlanSectionProps) {
  return (
    <ModalSection title="Decisive experiment">
      <h4>Primary hypothesis</h4>
      <p>{experiment.primary_hypothesis}</p>
      <h4>Secondary hypothesis</h4>
      <p>{experiment.secondary_hypothesis}</p>
      {experiment.claim_hierarchy && (
        <>
          <h4>Claim hierarchy</h4>
          <p>{experiment.claim_hierarchy}</p>
        </>
      )}
      <h4>Domains</h4>
      <BulletList items={experiment.domains} />
      {experiment.selection_protocol && (
        <>
          <h4>Selection protocol</h4>
          <p>{experiment.selection_protocol}</p>
        </>
      )}
      <h4>Baselines</h4>
      <BulletList items={experiment.baselines} />
      {experiment.resource_scalarization && (
        <>
          <h4>Resource scalarization</h4>
          <p>{experiment.resource_scalarization}</p>
        </>
      )}
      <h4>Ablations</h4>
      <BulletList items={experiment.ablations} />
      {experiment.action_ontology && (
        <>
          <h4>Action ontology</h4>
          <p>{experiment.action_ontology}</p>
        </>
      )}
      {experiment.primary_outcome && (
        <>
          <h4>Primary outcome</h4>
          <p>{experiment.primary_outcome}</p>
        </>
      )}
      {experiment.analysis && (
        <>
          <h4>Analysis</h4>
          <p>{experiment.analysis}</p>
        </>
      )}
      <h4>Decision rule</h4>
      <p>{experiment.decision_rule}</p>
      {falsifiers && (
        <>
          <h4>Claim-blocking falsifiers</h4>
          <BulletList items={falsifiers} />
        </>
      )}
    </ModalSection>
  );
}
