import { useCallback, useEffect, useRef, useState } from "react";
import {
  createCloud,
  fetchCloud,
  streamCloud,
  type CloudData,
  type CloudManifest,
} from "../lib/cloud";

export type CloudLoad = {
  manifest: CloudManifest | null;
  data: CloudData | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
};

type CloudState = Omit<CloudLoad, "retry">;

const EMPTY: CloudState = {
  manifest: null,
  data: null,
  loading: false,
  error: null,
};

export function useCloud(enabled: boolean): CloudLoad {
  const [state, setState] = useState<CloudState>(EMPTY);
  const [attempt, setAttempt] = useState(0);
  const cached = useRef<CloudState | null>(null);
  const retry = useCallback(() => {
    cached.current = null;
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setState(EMPTY);
      return;
    }
    if (cached.current) {
      setState(cached.current);
      return;
    }
    const controller = new AbortController();
    setState({ ...EMPTY, loading: true });
    fetchCloud(controller.signal)
      .then(async (manifest) => {
        if (controller.signal.aborted) return;
        const data = createCloud(manifest);
        setState({ manifest, data, loading: true, error: null });
        await streamCloud(manifest, data, controller.signal, (step) => {
          if (controller.signal.aborted) return;
          setState((current) =>
            current.data === data
              ? {
                  manifest,
                  data,
                  loading: step.loaded < step.total,
                  error: null,
                }
              : current,
          );
        });
        if (controller.signal.aborted) return;
        const complete = { manifest, data, loading: false, error: null };
        cached.current = complete;
        setState((current) => (current.data === data ? complete : current));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState((current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : "Paper cloud failed",
        }));
      });
    return () => controller.abort();
  }, [attempt, enabled]);

  return { ...state, retry };
}
