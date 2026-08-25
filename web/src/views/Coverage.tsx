import { CircleDot, FileText } from "lucide-react";
import { CoverageMini } from "../components/shared/Coverage";
import { PageHead } from "../components/shared/Head";
import { getCoverageSnapshot, percentageOfTotal } from "../lib/coverage";
import { labelOf } from "../lib/text";
import type { Atlas } from "../types";

type CoverageViewProps = {
  atlas: Atlas;
};

function AccessCopy({ partial }: { partial: number }) {
  return (
    <p>
      Adapter support describes whether the pipeline knows how to fetch a source. It
      does not mean that the paper already has a full reading; contextual links are
      classified separately and never receive fabricated paper reviews. Reviewable text
      requires usable extraction on at least 85% of pages.{" "}
      {partial > 0 ? (
        <>Partial extracts remain visible below but do not count as full text.</>
      ) : (
        <>No partial extracts remain in the current ledger.</>
      )}
    </p>
  );
}

export function CoverageView({ atlas }: CoverageViewProps) {
  const coverage = getCoverageSnapshot(atlas);
  const sourceAccess = coverage.sourceAccess;
  const partialTextCount = sourceAccess?.extractionStatuses.partial_text ?? 0;

  return (
    <main className="page">
      <PageHead
        icon={<FileText />}
        kicker="Coverage ledger"
        title="What has actually been read?"
        copy="This page is the guardrail against claiming corpus-wide synthesis before the evidence exists."
      />
      <section className="coverage-board">
        <div className="metric">
          <b>{coverage.collectionEntries.toLocaleString()}</b>
          <span>collection entries</span>
        </div>
        <div className="metric">
          <b>{coverage.fulltextExtracted}</b>
          <span>full texts extracted</span>
        </div>
        <div className="metric">
          <b>{coverage.fullReadings}</b>
          <span>page-anchored readings</span>
        </div>
        <div className="metric">
          <b>{Math.max(0, coverage.fulltextExtracted - coverage.fullReadings)}</b>
          <span>extracted, awaiting review</span>
        </div>
        <CoverageMini
          papers={atlas.papers}
          counts={coverage.depthCounts}
          total={coverage.collectionEntries}
        />
      </section>

      {sourceAccess && (
        <section className="access-board">
          <header>
            <span>Source access</span>
            <h2>Retrieval routes are classified, not equally complete</h2>
            <AccessCopy partial={partialTextCount} />
          </header>
          <div className="access-metrics">
            <div>
              <b>{sourceAccess.adapterSupported.toLocaleString()}</b>
              <span>adapter-supported records</span>
            </div>
            <div>
              <b>{sourceAccess.adapterMissing.toLocaleString()}</b>
              <span>manual-review records</span>
            </div>
            <div>
              <b>{sourceAccess.supportedWithoutReadings.toLocaleString()}</b>
              <span>supported, awaiting full reading</span>
            </div>
            <div>
              <b>{sourceAccess.nonPaperRecords.toLocaleString()}</b>
              <span>classified contextual records</span>
            </div>
          </div>
          <div className="access-routes">
            {Object.entries(sourceAccess.routes)
              .sort((a, b) => b[1] - a[1])
              .map(([route, count]) => (
                <div key={route}>
                  <span>{labelOf(route)}</span>
                  <i>
                    <em
                      style={{
                        width: `${percentageOfTotal(count, sourceAccess.classifiedRecords)}%`,
                      }}
                    />
                  </i>
                  <b>{count.toLocaleString()}</b>
                </div>
              ))}
          </div>
          <div className="access-statuses">
            {Object.entries(sourceAccess.extractionStatuses).map(([status, count]) => (
              <span key={status}>
                {labelOf(status)} <b>{count.toLocaleString()}</b>
              </span>
            ))}
          </div>
        </section>
      )}

      <div className="callout">
        <CircleDot />
        <div>
          <h2>Completion gate</h2>
          <p>{coverage.completionRule}</p>
        </div>
      </div>
    </main>
  );
}
