import type { Atlas } from "../types";
import { basePath } from "./paths";
import { type AtlasCore, type PaperBundle, bundleError, mergeAtlas } from "./payload";
import { placeError } from "./place";

function hexDigest(bytes: ArrayBuffer): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("This browser cannot verify the paper asset");
  }
  return globalThis.crypto.subtle
    .digest("SHA-256", bytes)
    .then((digest) =>
      Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join(""),
    );
}

export async function fetchPapers(
  core: AtlasCore,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<Atlas> {
  const response = await fetcher(basePath(core.paper_asset.path, base), {
    signal,
    cache: "force-cache",
  });
  if (!response.ok) throw new Error(`Paper asset request failed (${response.status})`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== core.paper_asset.bytes) {
    throw new Error("Paper asset byte length does not match its core index");
  }
  const digest = await hexDigest(bytes);
  if (digest !== core.paper_asset.sha256) {
    throw new Error("Paper asset digest does not match its core index");
  }
  let bundle: unknown;
  try {
    bundle = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new Error("Paper asset is not valid UTF-8 JSON");
  }
  const error = bundleError(bundle, core.paper_asset);
  if (error) throw new Error(`Paper asset has an invalid shape: ${error}`);
  const atlas = mergeAtlas(core, bundle as PaperBundle);
  if (atlas.layout) {
    const placement = placeError(atlas.idea_layout, atlas.ideas, atlas.layout);
    if (placement) throw new Error(`Paper asset has an invalid shape: ${placement}`);
  }
  return atlas;
}
