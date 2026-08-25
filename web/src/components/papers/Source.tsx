import { ExternalLink } from "lucide-react";
import { isWebUrl } from "../../lib/guards";
import { labelOf } from "../../lib/text";
import type { FullReading } from "../../types";
import { ModalSection } from "../shared/Section";

function parseWebUrl(locator: string): URL | null {
  if (!isWebUrl(locator)) return null;
  try {
    return new URL(locator);
  } catch {
    return null;
  }
}

function sourcePageUrl(locator: string, page: number): string | null {
  const url = parseWebUrl(locator);
  if (!url) return null;
  const pathname = url.pathname.toLocaleLowerCase();
  const arxivPdf =
    (url.hostname === "arxiv.org" || url.hostname.endsWith(".arxiv.org")) &&
    pathname.startsWith("/pdf/");
  const pdfEndpoint = pathname.endsWith(".pdf") || pathname.endsWith("/pdf");
  if (!arxivPdf && !pdfEndpoint) return null;
  url.hash = `page=${page}`;
  return url.toString();
}

function ReadingProvenance({ reading }: { reading: FullReading }) {
  const provenance = reading.source_provenance;
  const sourceUrl = parseWebUrl(provenance.source_locator)?.toString();
  const sourceHash =
    provenance.source_format === "html"
      ? provenance.source_sha256
      : provenance.pdf_sha256;
  const sourceLabel =
    provenance.source_format === "html" ? "HTML source SHA-256" : "PDF SHA-256";
  return (
    <>
      <aside className="source-pin" aria-label="Pinned reading source">
        <b>Source revision pinned</b>
        <dl className="provenance-grid">
          <div className="wide">
            <dt>Source locator</dt>
            <dd>
              {sourceUrl ? (
                <a href={sourceUrl} target="_blank" rel="noreferrer">
                  {provenance.source_locator}{" "}
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
              ) : (
                <code>{provenance.source_locator}</code>
              )}
            </dd>
          </div>
          <div>
            <dt>Pages</dt>
            <dd>{provenance.page_count}</dd>
          </div>
          <div>
            <dt>Review pass</dt>
            <dd>
              <code>{provenance.review_pass}</code>
            </dd>
          </div>
          <div className="wide">
            <dt>Extracted</dt>
            <dd>
              <time dateTime={provenance.extracted_at}>{provenance.extracted_at}</time>
            </dd>
          </div>
          <div className="wide provenance-hash">
            <dt>{sourceLabel}</dt>
            <dd>
              <code>{sourceHash}</code>
            </dd>
          </div>
          <div className="wide provenance-hash">
            <dt>Text SHA-256</dt>
            <dd>
              <code>{provenance.text_sha256}</code>
            </dd>
          </div>
        </dl>
      </aside>
      {reading.verification && (
        <ModalSection title="Verification lineage">
          <dl className="provenance-grid verification-grid">
            <div>
              <dt>Reviewer</dt>
              <dd>{reading.verification.reviewer_id}</dd>
            </div>
            <div>
              <dt>Checked</dt>
              <dd>
                <time dateTime={reading.verification.checked_at}>
                  {reading.verification.checked_at}
                </time>
              </dd>
            </div>
            <div className="wide">
              <dt>Passage check</dt>
              <dd>{reading.verification.passage_check}</dd>
            </div>
            <div className="wide">
              <dt>Competitor check</dt>
              <dd>{reading.verification.competitor_check}</dd>
            </div>
          </dl>
        </ModalSection>
      )}
    </>
  );
}

export function ReadingEvidence({ reading }: { reading: FullReading }) {
  return (
    <>
      <ReadingProvenance reading={reading} />
      <ModalSection title="Review question">
        <p className="modal-thesis">{reading.question}</p>
      </ModalSection>
      <ModalSection title="Page-anchored findings">
        <div className="finding-list">
          {reading.key_findings.map((finding, index) => (
            <article className="finding-card" key={finding.claim}>
              <b>{index + 1}</b>
              <div>
                {finding.attribution && (
                  <span className="finding-attribution">
                    Attribution · {labelOf(finding.attribution)}
                  </span>
                )}
                <h4>{finding.claim}</h4>
                <p>{finding.evidence}</p>
                <div className="anchor-row">
                  {finding.anchors.map((anchor) => {
                    const pageUrl = sourcePageUrl(
                      reading.source_provenance.source_locator,
                      anchor.page,
                    );
                    const label = `p. ${anchor.page} · ${anchor.section}`;
                    return pageUrl ? (
                      <a
                        href={pageUrl}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open pinned source at page ${anchor.page}, ${anchor.section}`}
                        key={`${anchor.page}-${anchor.section}`}
                      >
                        {label} <ExternalLink size={10} aria-hidden="true" />
                      </a>
                    ) : (
                      <span key={`${anchor.page}-${anchor.section}`}>{label}</span>
                    );
                  })}
                </div>
              </div>
            </article>
          ))}
        </div>
      </ModalSection>
    </>
  );
}
