import { GitCompareArrows, Grid3X3 } from "lucide-react";
import { independentlyRankedIdeas } from "../../lib/portfolio";
import { labelOf } from "../../lib/text";
import type { Atlas } from "../../types";
import type { ReadingBalanceRow } from "../../lib/insights";
import { ChartDataTable, VizHead } from "./Primitives";

export function ReadingBalance({ rows }: { rows: ReadingBalanceRow[] }) {
  return (
    <article className="viz-card balance-card">
      <VizHead
        icon={<GitCompareArrows />}
        title="Paper profiles × page-anchored coverage"
        copy="How do research-area shares compare between paper profiles and page-anchored readings?"
      />
      <div className="balance-bars" aria-hidden="true">
        {rows.map((row) => (
          <div key={row.id}>
            <span title={row.label}>{row.label}</span>
            <i>
              <em style={{ width: `${row.paperShare * 100}%` }} />
              <em style={{ width: `${row.reviewedShare * 100}%` }} />
            </i>
            <b>{Math.round(row.paperShare * 100)}%</b>
            <b>{Math.round(row.reviewedShare * 100)}%</b>
          </div>
        ))}
      </div>
      <div className="balance-legend" aria-hidden="true">
        <span>
          <i /> Paper profiles
        </span>
        <span>
          <i /> Page-anchored readings
        </span>
      </div>
      <small className="chart-note">
        Independent normalized distributions. A paper can contribute to more than one
        research area.
      </small>
      <ChartDataTable
        label="Paper profiles and page-anchored reading research-area footprint"
        columns={[
          "Research area",
          "Papers",
          "Paper share",
          "Page-anchored readings",
          "Reading share",
        ]}
        rows={rows.map((row) => [
          row.label,
          row.papers,
          `${(row.paperShare * 100).toFixed(1)}%`,
          row.reviewed,
          `${(row.reviewedShare * 100).toFixed(1)}%`,
        ])}
      />
    </article>
  );
}

export function FactorHeatmap({ atlas }: { atlas: Atlas }) {
  const ideas = independentlyRankedIdeas(atlas.ideas);
  const factors = ideas[0]?.feasibility.factors ?? [];
  const factorRows = ideas.map((idea) => {
    const factorsById = new Map(
      idea.feasibility.factors.map((factor) => [factor.id, factor]),
    );
    return {
      idea,
      factors: factors.map((factor) => factorsById.get(factor.id)!),
    };
  });

  return (
    <article className="viz-card factor-card">
      <VizHead
        icon={<Grid3X3 />}
        title="Idea feasibility factors"
        copy="Which practical constraint drives each independently ranked score?"
      />
      <div className="factor-scroll" aria-hidden="true">
        <div
          className="factor-map"
          style={{
            gridTemplateColumns: `minmax(340px, 2fr) 60px repeat(${factors.length}, minmax(110px, 1fr))`,
          }}
        >
          <b>Research idea</b>
          <b>Score</b>
          {factors.map((factor) => (
            <b key={factor.id}>{labelOf(factor.id)}</b>
          ))}
          {factorRows.flatMap(({ idea, factors: rowFactors }) => [
            <span key={`${idea.id}-label`} title={idea.brief.title}>
              {idea.brief.title}
            </span>,
            <strong key={`${idea.id}-score`}>
              {idea.feasibility.score.toFixed(1)}
            </strong>,
            ...rowFactors.map((factor) => {
              const ratio = factor.score / Math.max(0.01, factor.max);
              return (
                <i
                  key={`${idea.id}-${factor.id}`}
                  title={`${idea.brief.title} — ${labelOf(factor.id)}: ${factor.score.toFixed(1)} / ${factor.max.toFixed(1)}. ${factor.rationale}`}
                  style={{ background: `rgba(189, 120, 59, ${0.07 + ratio * 0.76})` }}
                >
                  {factor.score.toFixed(1)}
                </i>
              );
            }),
          ])}
        </div>
      </div>
      <small className="chart-note">
        Every total uses the same five-factor rubric and one-decimal 1–10 score. Work
        packages remain nested under their parent programs and are excluded here.
      </small>
      <ChartDataTable
        label="Idea feasibility factor scores"
        columns={[
          "Research idea",
          "Total",
          ...factors.map((factor) => labelOf(factor.id)),
        ]}
        rows={factorRows.map(({ idea, factors: rowFactors }) => [
          idea.brief.title,
          idea.feasibility.score.toFixed(1),
          ...rowFactors.map(
            (factor) => `${factor.score.toFixed(1)} / ${factor.max.toFixed(1)}`,
          ),
        ])}
      />
    </article>
  );
}
