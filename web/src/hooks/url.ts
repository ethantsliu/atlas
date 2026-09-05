import { useCallback, useEffect, useRef, useState } from "react";
import { APP_VIEWS, type AppView } from "../components/Header";
import { ALL_NODE_KINDS } from "../lib/graph";
import { formatCamera, parseCamera, type CameraView } from "../lib/camera";
import type { GraphNodeKind } from "../types";
import type { LayoutMode } from "./layout";
import type { RenderMode } from "./webgl";

export type { LayoutMode } from "./layout";

export type AtlasUrlState = {
  view: AppView;
  query: string;
  selected: string | null;
  kinds: GraphNodeKind[];
  minFeasibility: number;
  focus: string | null;
  layout: LayoutMode;
  render: RenderMode;
  camera: CameraView | null;
};

export type UrlPatch =
  Partial<AtlasUrlState> | ((state: AtlasUrlState) => Partial<AtlasUrlState>);

export type UrlMode = "replace" | "push";

type UrlHost = {
  location: { href: string };
  history: Pick<History, "pushState" | "replaceState">;
  addEventListener: Window["addEventListener"];
  removeEventListener: Window["removeEventListener"];
};

const VIEW_CODES: Record<AppView, string> = {
  map: "m",
  daily: "d",
  insights: "i",
  library: "l",
  briefs: "b",
  coverage: "c",
};

const KIND_CODES: Record<GraphNodeKind, string> = {
  topic: "t",
  trick: "r",
  paper: "p",
  idea: "i",
};

const DEFAULT_KINDS = [...ALL_NODE_KINDS];

export const DEFAULT_URL_STATE: AtlasUrlState = {
  view: "map",
  query: "",
  selected: null,
  kinds: [...DEFAULT_KINDS],
  minFeasibility: 1,
  focus: null,
  layout: "semantic",
  render: "3d",
  camera: null,
};

const CODE_VIEWS = new Map(
  Object.entries(VIEW_CODES).map(([view, code]) => [code, view]),
);
const CODE_KINDS = new Map(
  Object.entries(KIND_CODES).map(([kind, code]) => [code, kind]),
);

function validText(value: string | null, max: number): string | null {
  if (!value || value.length > max || /[\u0000-\u001f\u007f]/u.test(value)) return null;
  return value;
}

function validId(value: string | null): string | null {
  const text = validText(value, 240);
  return text && /^[\p{L}\p{N}][\p{L}\p{N}:._~@/+\-]*$/u.test(text) ? text : null;
}

function readKinds(params: URLSearchParams): GraphNodeKind[] {
  if (!params.has("k")) return [...DEFAULT_KINDS];
  const value = params.get("k") ?? "";
  if (value === "-") return [];
  if (!/^[trpi]{1,4}$/.test(value) || new Set(value).size !== value.length) {
    return [...DEFAULT_KINDS];
  }
  return value
    .split("")
    .map((code) => CODE_KINDS.get(code))
    .filter((kind): kind is GraphNodeKind => Boolean(kind));
}

function readScore(value: string | null): number {
  if (!value || !/^(?:[1-9](?:\.0|\.5)?|10(?:\.0)?)$/.test(value)) return 1;
  const score = Number(value);
  return score >= 1 && score <= 10 && score * 2 === Math.round(score * 2) ? score : 1;
}

function safeHash(hash: string): string {
  return /^#[\p{L}\p{N}][\p{L}\p{N}._~-]{0,63}$/u.test(hash) ? hash : "";
}

function cleanState(state: AtlasUrlState): AtlasUrlState {
  const view = APP_VIEWS.includes(state.view) ? state.view : "map";
  const kinds = ALL_NODE_KINDS.filter((kind) => state.kinds.includes(kind));
  const score = Number.isFinite(state.minFeasibility) ? state.minFeasibility : 1;
  return {
    view,
    query: validText(state.query, 200) ?? "",
    selected: validId(state.selected),
    kinds,
    minFeasibility:
      score >= 1 && score <= 10 && score * 2 === Math.round(score * 2) ? score : 1,
    focus: validId(state.focus),
    layout: "semantic",
    render: state.render === "3d" ? "3d" : "2d",
    camera: formatCamera(state.camera) ? state.camera : null,
  };
}

function readRender(params: URLSearchParams): RenderMode {
  if (params.get("d") === "2") return "2d";
  if (params.get("d") === "3") return "3d";
  return "3d";
}

function sameKinds(left: readonly GraphNodeKind[], right: readonly GraphNodeKind[]) {
  return (
    left.length === right.length && left.every((kind, index) => kind === right[index])
  );
}

export function decodeUrl(input: string | URL): AtlasUrlState {
  let url: URL;
  try {
    url = input instanceof URL ? input : new URL(input, "https://atlas.invalid/");
  } catch {
    return { ...DEFAULT_URL_STATE, kinds: [...DEFAULT_KINDS] };
  }
  const atlasHash = url.hash.startsWith("#?");
  const params = atlasHash
    ? new URLSearchParams(url.hash.slice(2))
    : new URLSearchParams();
  const view = CODE_VIEWS.get(params.get("v") ?? "") as AppView | undefined;
  return {
    view: view ?? "map",
    query: validText(params.get("q"), 200) ?? "",
    selected: validId(params.get("s")),
    kinds: readKinds(params),
    minFeasibility: readScore(params.get("f")),
    focus: validId(params.get("x")),
    layout: "semantic",
    render: readRender(params),
    camera: parseCamera(params.get("c")),
  };
}

export function encodeUrl(state: AtlasUrlState, base: string | URL): URL {
  const clean = cleanState(state);
  const url =
    base instanceof URL ? new URL(base) : new URL(base, "https://atlas.invalid/");
  const priorHash = safeHash(url.hash);
  const params = new URLSearchParams();
  if (clean.view !== "map") params.set("v", VIEW_CODES[clean.view]);
  if (clean.query) params.set("q", clean.query);
  if (clean.selected) params.set("s", clean.selected);
  if (!sameKinds(clean.kinds, DEFAULT_KINDS)) {
    params.set("k", clean.kinds.map((kind) => KIND_CODES[kind]).join("") || "-");
  }
  if (clean.minFeasibility !== 1) params.set("f", String(clean.minFeasibility));
  if (clean.focus) params.set("x", clean.focus);
  const camera = clean.view === "map" ? formatCamera(clean.camera) : null;
  if (camera) params.set("c", camera);
  if (clean.render === "2d") params.set("d", "2");
  const encoded = params.toString();
  url.search = "";
  url.hash = encoded ? `?${encoded}` : priorHash;
  return url;
}

export function saveUrl(
  state: AtlasUrlState,
  mode: UrlMode = "replace",
  host: UrlHost = window,
): void {
  const url = encodeUrl(state, host.location.href);
  const path = `${url.pathname}${url.search}${url.hash}`;
  if (mode === "push") host.history.pushState(null, "", path);
  else host.history.replaceState(null, "", path);
}

export function watchUrl(
  restore: (state: AtlasUrlState) => void,
  host: UrlHost = window,
): () => void {
  const onPop = () => restore(decodeUrl(host.location.href));
  host.addEventListener("popstate", onPop);
  return () => host.removeEventListener("popstate", onPop);
}

export function useAtlasUrl() {
  const [state, setState] = useState<AtlasUrlState>(() =>
    decodeUrl(window.location.href),
  );
  const stateRef = useRef(state);

  useEffect(
    () =>
      watchUrl((next) => {
        stateRef.current = next;
        setState(next);
      }),
    [],
  );

  const update = useCallback((patch: UrlPatch, mode: UrlMode = "replace") => {
    const current = stateRef.current;
    const changes = typeof patch === "function" ? patch(current) : patch;
    const next = cleanState({ ...current, ...changes, camera: null });
    stateRef.current = next;
    setState(next);
    saveUrl(next, mode);
  }, []);

  const replace = useCallback((patch: UrlPatch) => update(patch, "replace"), [update]);
  const push = useCallback((patch: UrlPatch) => update(patch, "push"), [update]);
  const shareUrl = useCallback(
    (camera: CameraView | null = null, render: RenderMode = state.render) =>
      encodeUrl({ ...state, camera, render }, window.location.href).toString(),
    [state],
  );

  return { state, replace, push, shareUrl };
}
