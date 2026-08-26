import { useEffect, useState } from "react";
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
};

const EMPTY: CloudLoad = {
  manifest: null,
  data: null,
  loading: false,
  error: null,
};

export function useCloud(enabled: boolean): CloudLoad {
  const [state, setState] = useState<CloudLoad>(EMPTY);

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
  }, [enabled]);

  return state;
}
