import { useEffect, useState } from "react";
import { hostedConfig, searchHostedFeed } from "../lib/hosted";
import type { DailyPaper, HostedPaper } from "../types";

type SearchState = {
  papers: HostedPaper[];
  total: number;
  loading: boolean;
  error: string | null;
};

const EMPTY: SearchState = { papers: [], total: 0, loading: false, error: null };

export function useSearch(
  query: string,
  lane: "all" | DailyPaper["relevance"]["lane"],
  shortlist: boolean,
  page: number,
  enabled: boolean,
  limit = 30,
) {
  const [state, setState] = useState<SearchState>(EMPTY);

  useEffect(() => {
    if (!enabled || query.trim().length < 2) {
      setState(EMPTY);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      async function runSearch() {
        try {
          const config = hostedConfig();
          if (!config) throw new Error("Hosted search is not configured");
          const result = await searchHostedFeed(
            config,
            {
              query: query.trim(),
              lane: lane === "all" ? undefined : lane,
              shortlist,
              limit,
              offset: (page - 1) * limit,
            },
            controller.signal,
          );
          if (!controller.signal.aborted) {
            setState({ ...result, loading: false, error: null });
          }
        } catch (error) {
          if (!controller.signal.aborted) {
            setState({
              papers: [],
              total: 0,
              loading: false,
              error: error instanceof Error ? error.message : "Hosted search failed",
            });
          }
        }
      }

      void runSearch();
    }, 250);
    setState((prior) => ({ ...prior, loading: true, error: null }));
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, lane, limit, page, query, shortlist]);

  return state;
}
