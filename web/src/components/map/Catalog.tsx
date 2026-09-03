import { useEffect, useState } from "react";
import { fetchCatalogSummary, type CatalogSummary } from "../../lib/catalog";

export function catalogDescription(summary: CatalogSummary, ideas: number): string {
  return `${summary.broadAreas.toLocaleString()} broad areas and ${summary.techniqueFamilies.toLocaleString()} technique families are navigation lenses. The full ${summary.sourceCount.toLocaleString()}-paper catalog adds ${summary.arxivSubjects.toLocaleString()} arXiv subjects and ${summary.candidateDirections.toLocaleString()} of ${summary.eligibleDirections.toLocaleString()} qualifying candidate directions. The ${ideas.toLocaleString()} ideas remain separately screened briefs.`;
}

export function CatalogCopy({ enabled, ideas }: { enabled: boolean; ideas: number }) {
  const [summary, setSummary] = useState<CatalogSummary | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void fetchCatalogSummary(controller.signal)
      .then(setSummary)
      .catch(() => {
        if (!controller.signal.aborted) setSummary(null);
      });
    return () => controller.abort();
  }, [enabled]);

  return (
    <p className="range-copy catalog-copy">
      {summary
        ? catalogDescription(summary, ideas)
        : "Topics and tricks are curated navigation lenses, not one label per paper. Ideas are screened briefs rather than automatic claims."}
    </p>
  );
}
