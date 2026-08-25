import { Activity, CalendarRange, Grid3X3, Layers3, Target } from "lucide-react";
import {
  countSubstantiveReadings,
  getCoverageSnapshot,
  percentageOfTotal,
} from "../../lib/coverage";
import type { Atlas, Taxon } from "../../types";
import type { TopicEvidenceRow } from "../../lib/insights";
import { ChartDataTable, VizHead } from "./Primitives";

type TopicTrickHeatmapProps = {
  topicRows: Taxon[];
  trickColumns: Taxon[];
  matrix: Map<string, number>;
};

export function TopicTrickHeatmap({
  topicRows,
  trickColumns,
  matrix,
}: TopicTrickHeatmapProps) {
  const matrixMax = Math.max(1, ...matrix.values());

  return (
    <article className="viz-card heatmap-card">
      <VizHead
        icon={<Grid3X3 />}
        title="Topic × technique density"
        copy="Which mechanisms recur across research areas?"
      />
      <span className="heatmap-hint" aria-hidden="true">
        Swipe to explore all techniques →
      </span>
      <div className="heatmap-scroll" aria-hidden="true">
        <div
          className="heatmap"
          style={{
            gridTemplateColumns: `145px repeat(${trickColumns.length}, minmax(48px,1fr))`,
          }}
        >
          <span />
          {trickColumns.map((trick) => (
            <b className="col-label" key={trick.id}>
              {trick.label}
            </b>
          ))}
          {topicRows.flatMap((topic) => [
            <b className="row-label" key={`label-${topic.id}`}>
              {topic.label}
            </b>,
            ...trickColumns.map((trick) => {
              const value = matrix.get(`${topic.id}|${trick.id}`) ?? 0;
              const alpha = Math.pow(value / matrixMax, 0.45);
              return (
                <i
                  key={`${topic.id}-${trick.id}`}
                  title={`${topic.label} × ${trick.label}: ${value} papers`}
                  style={{
                    background: `rgba(101, 131, 109, ${0.06 + alpha * 0.78})`,
                  }}
                >
                  <em>{value || ""}</em>
                </i>
              );
            }),
          ])}
        </div>
      </div>
      <div className="scale">
        <span>Sparse</span>
        <i />
        <span>Dense</span>
      </div>
      <ChartDataTable
        label="Topic by technique paper-entry counts"
        columns={["Research area", ...trickColumns.map((trick) => trick.label)]}
        rows={topicRows.map((topic) => [
          topic.label,
          ...trickColumns.map((trick) => matrix.get(`${topic.id}|${trick.id}`) ?? 0),
        ])}
      />
    </article>
  );
}

export function EvidenceMaturity({
  atlas,
  researchEntryTotal,
}: {
  atlas: Atlas;
  researchEntryTotal: number;
}) {
  const coverage = getCoverageSnapshot(atlas);
  const read = countSubstantiveReadings(coverage.depthCounts);
  const abstracts = coverage.depthCounts.abstract ?? 0;
  const readPercent = percentageOfTotal(read, researchEntryTotal);
  const routedPercent = percentageOfTotal(read + abstracts, researchEntryTotal);

  return (
    <article className="viz-card evidence-card">
      <VizHead
        icon={<Target />}
        title="Evidence maturity"
        copy="How much of the corpus supports synthesis now?"
      />
      <div className="rings">
        <div
          className="ring"
          style={{
            background: `conic-gradient(#65836d 0 ${readPercent}%, #55748c 0 ${routedPercent}%, #ded6ca 0)`,
          }}
        >
          <div>
            <b>{Math.round(readPercent)}%</b>
            <span>full text</span>
          </div>
        </div>
        <div className="depth-list">
          <p>
            <i className="full" />
            <span>Full text / verified</span>
            <b>{read}</b>
          </p>
          <p>
            <i className="abs" />
            <span>Abstract</span>
            <b>{abstracts}</b>
          </p>
          <p>
            <i />
            <span>Metadata only</span>
            <b>{coverage.depthCounts.metadata ?? 0}</b>
          </p>
        </div>
      </div>
      <small className="chart-note">
        Full text means a page-anchored reading; verified adds an independent passage
        and competitor check. Coverage is not confidence.
      </small>
      <ChartDataTable
        label="Evidence maturity counts"
        columns={["Reading depth", "Paper entries"]}
        rows={[
          ["Full text / verified", read],
          ["Abstract", abstracts],
          ["Metadata only", coverage.depthCounts.metadata ?? 0],
        ]}
      />
    </article>
  );
}

export function TopicDistribution({ topics }: { topics: Taxon[] }) {
  const maximum = topics[0]?.paper_count ?? 1;

  return (
    <article className="viz-card">
      <VizHead
        icon={<Activity />}
        title="Research-area distribution"
        copy="What dominates the collection after content routing?"
      />
      <div className="bars">
        {topics.map((topic, index) => (
          <div key={topic.id}>
            <span>{topic.label}</span>
            <i>
              <em
                style={{
                  width: `${(topic.paper_count / maximum) * 100}%`,
                  background: index < 3 ? "#a34f59" : "#55748c",
                }}
              />
            </i>
            <b>{topic.paper_count}</b>
          </div>
        ))}
      </div>
      <ChartDataTable
        label="Research-area paper-entry counts"
        columns={["Research area", "Paper entries"]}
        rows={topics.map((topic) => [topic.label, topic.paper_count])}
      />
    </article>
  );
}

export function TopicEvidenceCoverage({ rows }: { rows: TopicEvidenceRow[] }) {
  return (
    <article className="viz-card">
      <VizHead
        icon={<Layers3 />}
        title="Evidence depth by research area"
        copy="Where is the corpus ready for synthesis, and where is it still metadata-heavy?"
      />
      <div className="coverage-bars" aria-hidden="true">
        {rows.map((row) => (
          <div key={row.id}>
            <span title={row.label}>{row.label}</span>
            <i
              title={`${row.label}: ${row.fullText} full text, ${row.abstract} abstract, ${row.metadata} metadata`}
            >
              <em
                className="coverage-full"
                style={{ width: `${(row.fullText / Math.max(1, row.total)) * 100}%` }}
              />
              <em
                className="coverage-abstract"
                style={{ width: `${(row.abstract / Math.max(1, row.total)) * 100}%` }}
              />
              <em
                className="coverage-metadata"
                style={{ width: `${(row.metadata / Math.max(1, row.total)) * 100}%` }}
              />
            </i>
            <b>{row.total}</b>
          </div>
        ))}
      </div>
      <div className="coverage-legend" aria-hidden="true">
        <span>
          <i className="coverage-full" /> Full text
        </span>
        <span>
          <i className="coverage-abstract" /> Abstract
        </span>
        <span>
          <i className="coverage-metadata" /> Metadata
        </span>
      </div>
      <small className="chart-note">
        Papers can belong to more than one area; each bar is normalized within its
        research area.
      </small>
      <ChartDataTable
        label="Evidence depth counts by research area"
        columns={["Research area", "Full text", "Abstract", "Metadata", "Total"]}
        rows={rows.map((row) => [
          row.label,
          row.fullText,
          row.abstract,
          row.metadata,
          row.total,
        ])}
      />
    </article>
  );
}

export function PublicationTimeline({ years }: { years: Array<[number, number]> }) {
  const maximum = Math.max(1, ...years.map(([, count]) => count));

  return (
    <article className="viz-card">
      <VizHead
        icon={<CalendarRange />}
        title="Publication timeline"
        copy="How much recent work is represented?"
      />
      <div className="timeline" aria-hidden="true">
        {years.map(([year, count]) => (
          <div key={year}>
            <i
              style={{ height: `${Math.max(3, (count / maximum) * 100)}%` }}
              title={`${year}: ${count} papers`}
            />
            <b>{count}</b>
            <span>{year}</span>
          </div>
        ))}
      </div>
      <small className="chart-note">
        Uses arXiv publication metadata; records without dates are excluded.
      </small>
      <ChartDataTable
        label="Publication timeline counts"
        columns={["Year", "Paper entries"]}
        rows={years}
      />
    </article>
  );
}
