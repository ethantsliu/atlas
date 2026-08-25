import { useMemo } from "react";
import { BarChart3, Sparkles, Target } from "lucide-react";
import { buildFeasibilityBins, layoutFeasibilityFrontier } from "../../lib/insights";
import { independentlyRankedIdeas } from "../../lib/portfolio";
import { labelOf } from "../../lib/text";
import type { Atlas, Taxon } from "../../types";
import { ChartDataTable, VizHead } from "./Primitives";

export function FeasibilityFrontier({ atlas }: { atlas: Atlas }) {
  const rankedIdeas = useMemo(
    () => independentlyRankedIdeas(atlas.ideas),
    [atlas.ideas],
  );
  const points = useMemo(() => layoutFeasibilityFrontier(rankedIdeas), [rankedIdeas]);
  const workPackageCount = atlas.ideas.length - rankedIdeas.length;

  return (
    <article className="viz-card frontier-card">
      <VizHead
        icon={<Target />}
        title="Idea feasibility frontier"
        copy="Which ideas combine evidence confidence with practical testability?"
      />
      <svg
        viewBox="0 0 620 260"
        role="img"
        aria-label="Idea feasibility versus confidence scatter plot"
      >
        <desc>
          Exact overlaps are separated deterministically around their shared data
          coordinate; positions stay close to the original values.
        </desc>
        <line x1="45" y1="220" x2="600" y2="220" />
        <line x1="45" y1="20" x2="45" y2="220" />
        <text x="500" y="250">
          Evidence confidence →
        </text>
        <text transform="translate(14 155) rotate(-90)">Feasibility →</text>
        {points.map(({ idea, x, y, overlapCount }) => {
          const researchedDraft = idea.brief.status === "researched-draft";
          const label =
            idea.brief.title +
            ": " +
            idea.feasibility.score.toFixed(1) +
            " feasibility, " +
            Math.round(idea.brief.confidence * 100) +
            "% evidence confidence" +
            (overlapCount > 1
              ? ", one of " + overlapCount + " ideas at this coordinate"
              : "");
          return (
            <circle
              key={idea.id}
              cx={x}
              cy={y}
              r={researchedDraft ? 7 : 3.3}
              className={researchedDraft ? "flagship-dot" : "idea-dot"}
            >
              <title>{label}</title>
            </circle>
          );
        })}
      </svg>
      <small className="chart-note">
        Upper-right ideas are easiest to test with stronger current support. Exact
        overlaps are separated slightly for visibility. Small points are screening
        estimates; gold points are researched drafts. Scientific importance is separate.
        {workPackageCount > 0 &&
          ` ${workPackageCount} subordinate work ${workPackageCount === 1 ? "package is" : "packages are"} scored inside the program view, not ranked here as independent programs.`}
      </small>
      <ChartDataTable
        label="Idea feasibility and evidence-confidence values"
        columns={["Idea", "Feasibility", "Evidence confidence", "Status"]}
        rows={points.map(({ idea }) => [
          idea.brief.title,
          idea.feasibility.score.toFixed(1),
          `${Math.round(idea.brief.confidence * 100)}%`,
          idea.brief.status,
        ])}
      />
    </article>
  );
}

export function FeasibilityDistribution({ atlas }: { atlas: Atlas }) {
  const rankedIdeas = useMemo(
    () => independentlyRankedIdeas(atlas.ideas),
    [atlas.ideas],
  );
  const bins = useMemo(() => buildFeasibilityBins(rankedIdeas), [rankedIdeas]);
  const maximum = Math.max(1, ...bins.map((bin) => bin.total));

  return (
    <article className="viz-card feasibility-distribution-card">
      <VizHead
        icon={<BarChart3 />}
        title="Feasibility distribution"
        copy="How does the independently ranked idea portfolio spread across the 1–10 scale?"
      />
      <div className="feasibility-histogram" aria-hidden="true">
        {bins.map((bin) => (
          <div key={bin.label}>
            <i
              className="feasibility-stack"
              title={`${bin.label}: ${bin.researched} researched, ${bin.screening} screening-stage`}
            >
              <em
                className="histogram-researched"
                style={{ height: `${(bin.researched / maximum) * 100}%` }}
              />
              <em
                className="histogram-screening"
                style={{ height: `${(bin.screening / maximum) * 100}%` }}
              />
            </i>
            <b>{bin.total || ""}</b>
            <span>{bin.label}</span>
          </div>
        ))}
      </div>
      <div className="coverage-legend" aria-hidden="true">
        <span>
          <i className="histogram-researched" /> Researched draft
        </span>
        <span>
          <i className="histogram-screening" /> Screening estimate
        </span>
      </div>
      <small className="chart-note">
        Program work packages stay nested under their parent and are excluded from the
        independent distribution.
      </small>
      <ChartDataTable
        label="Idea feasibility score distribution"
        columns={[
          "Score interval",
          "Researched drafts",
          "Screening estimates",
          "Total",
        ]}
        rows={bins.map((bin) => [bin.label, bin.researched, bin.screening, bin.total])}
      />
    </article>
  );
}

export function TechniqueFootprint({ techniques }: { techniques: Taxon[] }) {
  return (
    <article className="viz-card">
      <VizHead
        icon={<Sparkles />}
        title="Reusable-technique footprint"
        copy="Which reusable mechanisms appear most often across the paper corpus?"
      />
      <div className="fingerprint">
        {techniques.map((technique) => (
          <div key={technique.id} style={{ flexGrow: technique.paper_count }}>
            <b>{technique.label}</b>
            <span>{technique.paper_count} paper entries</span>
          </div>
        ))}
      </div>
      <small className="chart-note">
        A paper can contribute to more than one reusable technique.
      </small>
      <ChartDataTable
        label="Reusable technique paper-entry counts"
        columns={["Reusable technique", "Paper entries"]}
        rows={techniques.map((technique) => [technique.label, technique.paper_count])}
      />
    </article>
  );
}
