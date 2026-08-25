import { useMemo } from "react";
import { Sparkles } from "lucide-react";
import {
  EvidenceMaturity,
  PublicationTimeline,
  TopicDistribution,
  TopicEvidenceCoverage,
  TopicTrickHeatmap,
} from "./components/insights/Corpus";
import {
  FeasibilityDistribution,
  FeasibilityFrontier,
  TechniqueFootprint,
} from "./components/insights/Ideas";
import { FactorHeatmap, ReadingBalance } from "./components/insights/Portfolio";
import {
  buildEvidenceRows,
  buildTopicMatrix,
  buildReadingBalance,
  getRecentYears,
} from "./lib/insights";
import type { Atlas } from "./types";

type InsightsProps = {
  atlas: Atlas;
};

export default function Insights({ atlas }: InsightsProps) {
  const researchPapers = useMemo(
    () => atlas.papers.filter((paper) => paper.record_kind === "paper"),
    [atlas.papers],
  );
  const topicRows = useMemo(
    () => [...atlas.topics].sort((a, b) => b.paper_count - a.paper_count).slice(0, 11),
    [atlas.topics],
  );
  const trickColumns = useMemo(
    () => [...atlas.tricks].sort((a, b) => b.paper_count - a.paper_count).slice(0, 12),
    [atlas.tricks],
  );
  const matrix = useMemo(() => buildTopicMatrix(researchPapers), [researchPapers]);
  const years = useMemo(() => getRecentYears(researchPapers), [researchPapers]);
  const topicEvidenceRows = useMemo(
    () => buildEvidenceRows(researchPapers, topicRows.slice(0, 9)),
    [researchPapers, topicRows],
  );
  const reviewedPapers = useMemo(
    () =>
      researchPapers.filter((paper) =>
        ["full_text", "verified"].includes(paper.reading_depth),
      ),
    [researchPapers],
  );
  const readingBalance = useMemo(
    () => buildReadingBalance(researchPapers, reviewedPapers, atlas.topics),
    [researchPapers, reviewedPapers, atlas.topics],
  );
  const researchEntryTotal = atlas.meta.research_entry_count;

  return (
    <main className="insights-page">
      <header className="insights-head">
        <span>
          <Sparkles size={14} /> Corpus observatory
        </span>
        <h1>See the shape of the research space</h1>
        <p>
          Each view answers a different question: where the collection is dense, which
          techniques cross fields, how mature the evidence is, and which ideas offer the
          best near-term test.
        </p>
      </header>

      <section className="viz-grid">
        <TopicTrickHeatmap
          topicRows={topicRows}
          trickColumns={trickColumns}
          matrix={matrix}
        />
        <EvidenceMaturity atlas={atlas} researchEntryTotal={researchEntryTotal} />
        <TopicDistribution topics={topicRows} />
        <TopicEvidenceCoverage rows={topicEvidenceRows} />
        <ReadingBalance rows={readingBalance} />
        <PublicationTimeline years={years} />
        <FeasibilityFrontier atlas={atlas} />
        <FeasibilityDistribution atlas={atlas} />
        <FactorHeatmap atlas={atlas} />
        <TechniqueFootprint techniques={trickColumns} />
      </section>
    </main>
  );
}
