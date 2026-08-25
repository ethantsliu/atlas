import { useCallback, useEffect, useState } from "react";
import { fetchFullReading } from "../lib/readings";
import type { FullReading, Paper } from "../types";

export type FullReadingLoadState =
  | { status: "idle"; reading: null; error: null }
  | { status: "loading"; reading: null; error: null }
  | { status: "loaded"; reading: FullReading; error: null }
  | { status: "error"; reading: null; error: string };

type KeyedState = FullReadingLoadState & { requestKey: string };

function requestKey(paper: Paper): string {
  return [paper.full_reading_path, paper.stable_id, paper.reading_depth].join("|");
}

function initialState(paper: Paper): KeyedState {
  return {
    status: paper.full_reading_path ? "loading" : "idle",
    reading: null,
    error: null,
    requestKey: requestKey(paper),
  };
}

export function useFullReading(paper: Paper): {
  state: FullReadingLoadState;
  retry: () => void;
} {
  const key = requestKey(paper);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<KeyedState>(() => initialState(paper));

  useEffect(() => {
    const path = paper.full_reading_path;
    if (!path) {
      setState({
        status: "idle",
        reading: null,
        error: null,
        requestKey: key,
      });
      return;
    }

    if (!paper.stable_id || !["full_text", "verified"].includes(paper.reading_depth)) {
      setState({
        status: "error",
        reading: null,
        error: "The compact paper record has an invalid full-reading reference.",
        requestKey: key,
      });
      return;
    }

    const controller = new AbortController();
    setState({
      status: "loading",
      reading: null,
      error: null,
      requestKey: key,
    });
    void fetchFullReading({
      path,
      stableId: paper.stable_id,
      readingDepth: paper.reading_depth as FullReading["reading_depth"],
      signal: controller.signal,
    })
      .then((reading) => {
        if (controller.signal.aborted) return;
        setState({
          status: "loaded",
          reading,
          error: null,
          requestKey: key,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          reading: null,
          error:
            error instanceof Error
              ? error.message
              : "The full reading could not be loaded.",
          requestKey: key,
        });
      });

    return () => controller.abort();
  }, [attempt, key, paper.full_reading_path, paper.reading_depth, paper.stable_id]);

  const retry = useCallback(() => {
    setState({
      status: "loading",
      reading: null,
      error: null,
      requestKey: key,
    });
    setAttempt((value) => value + 1);
  }, [key]);

  const visibleState: FullReadingLoadState =
    state.requestKey === key ? state : initialState(paper);
  return { state: visibleState, retry };
}
