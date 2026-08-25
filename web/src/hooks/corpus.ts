import { useEffect, useMemo, useState } from "react";
import { hostedConfig, searchHostedCorpus, type HostedConfig } from "../lib/hosted";
import type { CorpusMatch } from "../types";

type CorpusState = {
  active: boolean;
  matches: CorpusMatch[];
  total: number;
  loading: boolean;
  error: string | null;
};

const EMPTY: CorpusState = {
  active: false,
  matches: [],
  total: 0,
  loading: false,
  error: null,
};

export function useCorpus(query: string, page: number, limit: number) {
  const setup = useMemo(() => {
    try {
      return { config: hostedConfig(), error: null };
    } catch (error) {
      return {
        config: null,
        error: error instanceof Error ? error.message : "Hosted search is invalid",
      };
    }
  }, []);
  const [state, setState] = useState<CorpusState>(EMPTY);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2 || !setup.config) {
      setState({ ...EMPTY, error: term.length >= 2 ? setup.error : null });
      return;
    }
    const config: HostedConfig = setup.config;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      async function runSearch() {
        try {
          const result = await searchHostedCorpus(
            config,
            term,
            limit,
            (page - 1) * limit,
            controller.signal,
          );
          if (!controller.signal.aborted) {
            setState({
              active: true,
              matches: result.matches,
              total: result.total,
              loading: false,
              error: null,
            });
          }
        } catch (error) {
          if (!controller.signal.aborted) {
            setState({
              ...EMPTY,
              error: error instanceof Error ? error.message : "Hosted search failed",
            });
          }
        }
      }

      void runSearch();
    }, 250);
    setState({ active: true, matches: [], total: 0, loading: true, error: null });
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [limit, page, query, setup]);

  return state;
}
