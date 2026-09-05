import { CircleDot, FileText } from "lucide-react";
import { CoverageMini } from "../components/shared/Coverage";
import { PageHead } from "../components/shared/Head";
import { useArchive } from "../hooks/archive";
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
      does not mean that the paper already has a full reading. Non-paper sources remain
      outside Paper coverage and never receive fabricated paper reviews. Reviewable text
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
  const archive = useArchive();
  const coverage = getCoverageSnapshot(atlas);
  const sourceAccess = coverage.sourceAccess;
  const partialTextCount = sourceAccess?.extractionStatuses.partial_text ?? 0;

  return (
    <main className="page">
      <PageHead
        icon={<FileText />}
        kicker="Coverage ledger"
        title="What has actually been read?"
        copy="Reading depth covers paper profiles, not every embedded paper in the arXiv map."
      />
      <section
        className="coverage-board"
        aria-label={`Reading depth for ${coverage.collectionEntries.toLocaleString()} paper profiles`}
      >
        <div className="metric">
          <b>{coverage.collectionEntries.toLocaleString()}</b>
          <span>paper profiles</span>
        </div>
        <div className="metric">
          <b>{coverage.fulltextExtracted}</b>
          <span>full-text sources extracted</span>
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
          label={`Exclusive reading depths among ${coverage.collectionEntries.toLocaleString()} paper profiles`}
        />
      </section>

      {archive && (
        <section className="access-board">
          <header>
            <span>arXiv map corpus</span>
            <h2>The full corpus stays mapped without loading every record at once</h2>
            <p>
              These papers are embedded from title, an abstract excerpt, and arXiv
              categories for discovery. They are not counted as read, reviewed, or full
              text above. Month metadata loads only when search or selection needs it.
            </p>
          </header>
          <div className="access-metrics">
            <div>
              <b>{archive.counts.all.toLocaleString()}</b>
              <span>arXiv source records</span>
            </div>
            <div>
              <b>
                {archive.shards
                  .reduce((total, shard) => total + shard.days, 0)
                  .toLocaleString()}
              </b>
              <span>complete UTC dates</span>
            </div>
          </div>
        </section>
      )}

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
