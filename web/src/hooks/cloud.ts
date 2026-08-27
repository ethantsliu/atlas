import { useCallback, useEffect, useState } from "react";
import {
  fetchCloud,
  loadCloud,
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
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) {
      setState(EMPTY);
      return;
    }
    const controller = new AbortController();
    setState({ ...EMPTY, loading: true });
    fetchCloud(controller.signal)
      .then(async (manifest) => ({
        manifest,
        data: await loadCloud(manifest, controller.signal),
      }))
      .then(({ manifest, data }) => {
        if (controller.signal.aborted) return;
        setState({ manifest, data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          ...EMPTY,
          error: error instanceof Error ? error.message : "Paper cloud failed",
        });
      });
    return () => controller.abort();
  }, [attempt, enabled]);

  return { ...state, retry };
}
