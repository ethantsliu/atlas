import type { Atlas } from "../types";
import { basePath } from "./paths";
import { type AtlasCore, coreError } from "./payload";

export async function fetchCore(
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<AtlasCore> {
  const response = await fetcher(basePath("/data/atlas.json", base), {
    signal,
    cache: "no-cache",
  });
  if (!response.ok) throw new Error(`Atlas request failed (${response.status})`);
  const core: unknown = await response.json();
  const error = coreError(core);
  if (error) throw new Error(`Atlas core has an invalid shape: ${error}`);
  return core as AtlasCore;
}

export async function fetchAtlas(
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<Atlas> {
  const core = await fetchCore(signal, fetcher, base);
  return (await import("./paper")).fetchPapers(core, signal, fetcher, base);
}
