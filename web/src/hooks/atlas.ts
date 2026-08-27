import { useCallback, useEffect, useState } from "react";
import { stageAtlas, type AtlasCore, type AtlasPreview } from "../lib/payload";
import { fetchCore } from "../lib/request";
import type { Atlas } from "../types";

type AtlasLoadState = {
  phase: "loading" | "core" | "papers" | "full" | "error";
  core: AtlasCore | null;
  preview: AtlasPreview | null;
  atlas: Atlas | null;
  error: string | null;
  retry: () => void;
  loadPapers: () => void;
  retryPapers: () => void;
  papersReady: boolean;
  papersLoading: boolean;
  papersError: string | null;
};

export function useAtlas(): AtlasLoadState {
  const [attempt, setAttempt] = useState(0);
  const [paperAttempt, setPaperAttempt] = useState(0);
  const [requested, setRequested] = useState(false);
  const loadPapers = useCallback(() => setRequested(true), []);
  const retryPapers = useCallback(() => {
    setRequested(true);
    setPaperAttempt((value) => value + 1);
  }, []);
  const retry = useCallback(() => {
    setRequested(false);
    setAttempt((value) => value + 1);
  }, []);
  const [state, setState] = useState<
    Omit<AtlasLoadState, "retry" | "loadPapers" | "retryPapers">
  >({
    phase: "loading",
    core: null,
    preview: null,
    atlas: null,
    error: null,
    papersReady: false,
    papersLoading: false,
    papersError: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    setState({
      phase: "loading",
      core: null,
      preview: null,
      atlas: null,
      error: null,
      papersReady: false,
      papersLoading: false,
      papersError: null,
    });

    async function loadCore() {
      try {
        const next = await fetchCore(controller.signal);
        if (controller.signal.aborted) return;
        setState({
          phase: "core",
          core: next,
          preview: stageAtlas(next),
          atlas: null,
          error: null,
          papersReady: false,
          papersLoading: false,
          papersError: null,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          phase: "error",
          core: null,
          preview: null,
          atlas: null,
          error: error instanceof Error ? error.message : "Atlas request failed",
          papersReady: false,
          papersLoading: false,
          papersError: null,
        });
      }
    }

    void loadCore();
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    const core = state.core;
    if (!core || !requested || state.papersReady) return;
    const activeCore: AtlasCore = core;
    const controller = new AbortController();
    setState((current) => ({
      ...current,
      phase: "papers",
      papersLoading: true,
      papersError: null,
    }));

    async function loadBundle() {
      try {
        const { fetchPapers } = await import("../lib/paper");
        const atlas = await fetchPapers(activeCore, controller.signal);
        if (controller.signal.aborted) return;
        setState((current) => ({
          ...current,
          phase: "full",
          atlas,
          error: null,
          papersReady: true,
          papersLoading: false,
          papersError: null,
        }));
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((current) => ({
          ...current,
          phase: "core",
          papersLoading: false,
          papersError:
            error instanceof Error ? error.message : "Paper asset request failed",
        }));
      }
    }

    void loadBundle();
    return () => controller.abort();
  }, [paperAttempt, requested, state.core, state.papersReady]);

  return { ...state, retry, loadPapers, retryPapers };
}
