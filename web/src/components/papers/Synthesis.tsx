import { labelOf } from "../../lib/text";
import type { FullReading } from "../../types";
import { BulletList } from "../shared/Bullets";
import { ModalSection } from "../shared/Section";

export function ReadingSynthesis({ reading }: { reading: FullReading }) {
  return (
    <div className="modal-columns">
      <div>
        <ModalSection title="Method">
          <h4>Core idea</h4>
          <p>{reading.method.core_idea}</p>
          <h4>Mechanism</h4>
          <p>{reading.method.mechanism}</p>
          <h4>Assumptions</h4>
          <BulletList items={reading.method.assumptions} />
        </ModalSection>
        <ModalSection title="Evaluations">
          <div className="evaluation-list">
            {reading.evaluations.map((evaluation) => (
              <article key={`${evaluation.setting}-${evaluation.metric}`}>
                <span>{evaluation.metric}</span>
                <b>{evaluation.result}</b>
                <p>{evaluation.setting}</p>
                <small>Comparison: {evaluation.baseline}</small>
              </article>
            ))}
          </div>
        </ModalSection>
        <ModalSection title="Reusable insights">
          <BulletList items={reading.reusable_insights} />
        </ModalSection>
      </div>
      <div>
        <ModalSection title="Techniques">
          <div className="technique-list">
            {reading.techniques.map((technique) => (
              <article key={technique.id}>
                <b>{labelOf(technique.id)}</b>
                <p>{technique.role}</p>
              </article>
            ))}
          </div>
        </ModalSection>
        <ModalSection title="Limitations">
          <BulletList items={reading.limitations} />
        </ModalSection>
        <ModalSection title="Failure modes">
          <BulletList items={reading.failure_modes} />
        </ModalSection>
        <ModalSection title="Open questions">
          <BulletList items={reading.open_questions} />
        </ModalSection>
      </div>
    </div>
  );
}
