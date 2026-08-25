import { useCallback, useEffect, useState } from "react";
import { fetchFeedDay, fetchFeedIndex } from "../lib/feed";
import { fetchHostedDay, fetchHostedIndex, hostedConfig } from "../lib/hosted";
import type { DailyDay, DailyIndex } from "../types";

type FeedState = {
  index: DailyIndex | null;
  day: DailyDay | null;
  selected: string;
  loading: boolean;
  error: string | null;
  source: "hosted" | "static";
  fallback: boolean;
  hostedDays: number;
};

export function mergeIndex(hosted: DailyIndex, archive: DailyIndex): DailyIndex {
  const days = new Map(archive.days.map((day) => [day.date, day]));
  hosted.days.forEach((day) => days.set(day.date, day));
  return {
    schema_version: 1,
    generated_at: hosted.generated_at,
    days: [...days.values()].sort((left, right) => right.date.localeCompare(left.date)),
  };
}

export function useFeed() {
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState("");
  const [state, setState] = useState<FeedState>({
    index: null,
    day: null,
    selected: "",
    loading: true,
    error: null,
    source: "static",
    fallback: false,
    hostedDays: 0,
  });
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setState((prior) => ({ ...prior, day: null, loading: true, error: null }));

    async function loadFeed() {
      try {
        let config = null;
        let source: FeedState["source"] = "static";
        let fallback = false;
        let index: DailyIndex;
        let hostedDates = new Set<string>();
        try {
          config = hostedConfig();
          if (config) {
            const [hostedIndex, archive] = await Promise.all([
              fetchHostedIndex(config, controller.signal),
              fetchFeedIndex(controller.signal),
            ]);
            hostedDates = new Set(hostedIndex.days.map((day) => day.date));
            index = mergeIndex(hostedIndex, archive);
          } else {
            index = await fetchFeedIndex(controller.signal);
          }
          source = config ? "hosted" : "static";
        } catch {
          index = await fetchFeedIndex(controller.signal);
          fallback = true;
        }
        const recent = index.days.find((item) => item.relevant_count > 0);
        const date = selected || recent?.date || index.days[0]?.date || "";
        const summary = index.days.find((item) => item.date === date);
        let day = null;
        if (summary) {
          try {
            day =
              config && source === "hosted" && hostedDates.has(date)
                ? await fetchHostedDay(config, date, controller.signal)
                : await fetchFeedDay(summary.path, controller.signal);
          } catch (error) {
            if (source !== "hosted") throw error;
            day = await fetchFeedDay(summary.path, controller.signal);
            source = "static";
            fallback = true;
          }
        }
        if (controller.signal.aborted) return;
        setState({
          index,
          day,
          selected: date,
          loading: false,
          error: null,
          source,
          fallback,
          hostedDays: hostedDates.size,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((prior) => ({
          ...prior,
          loading: false,
          source: "static",
          fallback: true,
          hostedDays: 0,
          error: error instanceof Error ? error.message : "Daily feed request failed",
        }));
      }
    }

    void loadFeed();
    return () => controller.abort();
  }, [attempt, selected]);

  return {
    ...state,
    selected: selected || state.selected,
    select: setSelected,
    retry,
  };
}
