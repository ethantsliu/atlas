import { useEffect, useState } from "react";
import { fetchCatalogSummary, type CatalogSummary } from "../lib/catalog";

export function useCatalogSummary(enabled: boolean): CatalogSummary | null {
  const [summary, setSummary] = useState<CatalogSummary | null>(null);

  useEffect(() => {
    if (!enabled) {
      setSummary(null);
      return;
    }
    const controller = new AbortController();
    void fetchCatalogSummary(controller.signal)
      .then(setSummary)
      .catch(() => {
        if (!controller.signal.aborted) setSummary(null);
      });
    return () => controller.abort();
  }, [enabled]);

  return summary;
}
