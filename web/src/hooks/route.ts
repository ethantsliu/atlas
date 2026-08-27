import { useEffect, useState } from "react";
import {
  cloudRange,
  type CloudData,
  type CloudManifest,
  type CloudPick,
  type CloudRelation,
} from "../lib/cloud";

type RouteState = {
  data: CloudRelation | null;
  loading: boolean;
  error: string | null;
};

const EMPTY: RouteState = { data: null, loading: false, error: null };

export function useRoute(
  manifest: CloudManifest | null,
  cloud: CloudData | null,
  pick: CloudPick | null,
  enabled: boolean,
): RouteState {
  const [state, setState] = useState<RouteState>(EMPTY);

  useEffect(() => {
    if (!enabled || !manifest || !cloud || !pick) {
      setState(EMPTY);
      return;
    }
    const range = cloudRange(cloud, pick.index);
    if (!manifest.anchors || !range?.routes) {
      setState({ ...EMPTY, error: "Connections are unavailable for this paper" });
      return;
    }
    const controller = new AbortController();
    setState({ data: null, loading: true, error: null });
    import("../lib/relation")
      .then(({ fetchRelation }) =>
        fetchRelation(manifest, range, pick.index, controller.signal),
      )
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : "Paper connections failed",
        });
      });
    return () => controller.abort();
  }, [cloud, enabled, manifest, pick]);

  return state;
}
