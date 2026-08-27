import { useEffect, useMemo, useState } from "react";
import { cloudRange, type CloudPick } from "../lib/cloud";
import { focusCloud } from "../lib/focus";
import type { AtlasRead } from "../lib/payload";
import type { CloudLoad } from "./cloud";
import { useRoute } from "./route";

export function useFocus(atlas: AtlasRead, history: CloudLoad, blocked: boolean) {
  const [pick, setPick] = useState<CloudPick | null>(null);
  const [focused, setFocused] = useState(false);
  const available = blocked ? null : history.data;
  const route = useRoute(history.manifest, history.data, pick, focused);
  const view = useMemo(
    () =>
      focused && history.data && pick
        ? focusCloud(atlas, history.data, pick, route.data)
        : null,
    [atlas, focused, history.data, pick, route.data],
  );
  const ready = Boolean(
    history.manifest?.anchors &&
    history.data &&
    pick &&
    cloudRange(history.data, pick.index)?.routes,
  );
  const error =
    focused && route.data && !view
      ? "Paper relation targets do not match this Atlas release"
      : route.error;

  useEffect(() => {
    if (!pick || available) return;
    setPick(null);
    setFocused(false);
  }, [available, pick]);

  function choose(next: CloudPick) {
    setPick(next);
    setFocused(false);
  }

  function clear() {
    setPick(null);
    setFocused(false);
  }

  function toggle() {
    setFocused((current) => !current);
  }

  return {
    pick,
    focused,
    data: available,
    hidden: focused,
    graph: view?.graph ?? null,
    mark: view?.mark ?? null,
    ready,
    loading: route.loading,
    error,
    choose,
    clear,
    toggle,
  };
}
