import { labelOf } from "../../lib/text";
import type { FullReading } from "../../types";
import { ModalSection } from "../shared/Section";

export function ReadingCompetition({ reading }: { reading: FullReading }) {
  return (
    <>
      <ModalSection title="Competitive landscape">
        <div className="landscape">
          {reading.competitive_landscape.map((competitor) => (
            <a
              href={competitor.url}
              target="_blank"
              rel="noreferrer"
              key={competitor.canonical_id}
            >
              <span>{competitor.relationship}</span>
              <b>{competitor.title}</b>
              <p>{competitor.difference}</p>
              {(competitor.source_kind ||
                competitor.checked_at ||
                competitor.source_version ||
                competitor.source_date) && (
                <dl
                  className="competitor-provenance"
                  aria-label={`Source verification for ${competitor.title}`}
                >
                  {competitor.source_kind && (
                    <div>
                      <dt>Source</dt>
                      <dd>{labelOf(competitor.source_kind)}</dd>
                    </div>
                  )}
                  {competitor.source_version && (
                    <div>
                      <dt>Version</dt>
                      <dd>{competitor.source_version}</dd>
                    </div>
                  )}
                  {competitor.source_date && (
                    <div>
                      <dt>Source date</dt>
                      <dd>
                        <time dateTime={competitor.source_date}>
                          {competitor.source_date}
                        </time>
                      </dd>
                    </div>
                  )}
                  {competitor.checked_at && (
                    <div>
                      <dt>Checked</dt>
                      <dd>
                        <time dateTime={competitor.checked_at}>
                          {competitor.checked_at}
                        </time>
                      </dd>
                    </div>
                  )}
                </dl>
              )}
            </a>
          ))}
        </div>
      </ModalSection>
      <ModalSection title="Novelty and review confidence">
        {typeof reading.novelty_assessment === "string" ? (
          <p className="novelty">
            <b>Novelty assessment:</b> {reading.novelty_assessment}
          </p>
        ) : (
          <div className="novelty structured-novelty">
            <h4>Author claim</h4>
            <p>{reading.novelty_assessment.author_claim}</p>
            {reading.novelty_assessment.evidence && (
              <>
                <h4>Evidence</h4>
                <p>{reading.novelty_assessment.evidence}</p>
              </>
            )}
            <h4>Reviewer inference</h4>
            <p>{reading.novelty_assessment.reviewer_inference}</p>
          </div>
        )}
        <p>{reading.reviewer_notes}</p>
      </ModalSection>
    </>
  );
}
