import { useCallback, useEffect, useState } from "react";
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

type CloudStore = {
  controller: AbortController;
  listeners: Set<(state: CloudState) => void>;
  promise: Promise<void>;
  state: CloudState;
};

const EMPTY: CloudState = {
  manifest: null,
  data: null,
  loading: false,
  error: null,
};

const LOADING: CloudState = { ...EMPTY, loading: true };
let shared: CloudStore | null = null;

function publish(store: CloudStore, state: CloudState): void {
  if (shared !== store) return;
  store.state = state;
  store.listeners.forEach((listener) => listener(state));
}

function makeStore(): CloudStore {
  const controller = new AbortController();
  const store: CloudStore = {
    controller,
    listeners: new Set(),
    promise: Promise.resolve(),
    state: LOADING,
  };
  shared = store;
  store.promise = fetchCloud(controller.signal)
    .then(async (manifest) => {
      if (controller.signal.aborted) return;
      const data = createCloud(manifest);
      publish(store, { manifest, data, loading: true, error: null });
      await streamCloud(manifest, data, controller.signal, (step) => {
        if (controller.signal.aborted) return;
        publish(store, {
          manifest,
          data,
          loading: step.loaded < step.total,
          error: null,
        });
      });
      if (controller.signal.aborted) return;
      publish(store, { manifest, data, loading: false, error: null });
    })
    .catch((error: unknown) => {
      if (controller.signal.aborted || shared !== store) return;
      publish(store, {
        ...store.state,
        loading: false,
        error: error instanceof Error ? error.message : "Paper cloud failed",
      });
      shared = null;
    });
  return store;
}

function subscribe(listener: (state: CloudState) => void): () => void {
  const store = shared ?? makeStore();
  store.listeners.add(listener);
  listener(store.state);
  return () => {
    store.listeners.delete(listener);
    if (store.listeners.size || !store.state.loading) return;
    if (shared === store) shared = null;
    store.controller.abort();
  };
}

export function resetCloud(): void {
  const store = shared;
  shared = null;
  if (store?.state.loading) store.controller.abort();
}

export function useCloud(enabled: boolean): CloudLoad {
  const [state, setState] = useState<CloudState>(EMPTY);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    resetCloud();
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setState(EMPTY);
      return;
    }
    return subscribe(setState);
  }, [attempt, enabled]);

  return { ...state, retry };
}
