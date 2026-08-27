import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

export const limits = {
  // One self-hosted typeface keeps canvas and DOM labels visually identical.
  shell: { requests: 3, raw: 304 * 1024, gzip: 112 * 1024 },
  map: { requests: 8, raw: 68 * 1024, gzip: 24 * 1024 },
  twoD: { requests: 4, raw: 220 * 1024, gzip: 76 * 1024 },
  threeD: { requests: 4, raw: 1500 * 1024, gzip: 410 * 1024 },
};

export function readManifest(root) {
  return JSON.parse(readFileSync(join(root, "dist/.vite/manifest.json"), "utf8"));
}

export function findEntry(manifest, predicate) {
  const key = Object.keys(manifest).find((candidate) =>
    predicate(manifest[candidate], candidate),
  );
  if (!key) throw new Error("Required production entry is missing");
  return key;
}

export function staticClosure(manifest, roots) {
  const found = new Set();
  const pending = [...roots];
  while (pending.length > 0) {
    const key = pending.pop();
    if (found.has(key)) continue;
    const entry = manifest[key];
    if (!entry) throw new Error(`Manifest entry is missing: ${key}`);
    found.add(key);
    pending.push(...(entry.imports ?? []));
  }
  return found;
}

export function outputAssets(manifest, keys) {
  const assets = new Set();
  for (const key of keys) {
    const entry = manifest[key];
    assets.add(entry.file);
    for (const file of entry.css ?? []) assets.add(file);
    for (const file of entry.assets ?? []) assets.add(file);
  }
  return assets;
}

export function subtractAssets(assets, loaded) {
  return new Set([...assets].filter((file) => !loaded.has(file)));
}

export function sizeProfile(root, assets) {
  const content = [...assets].map((file) => readFileSync(join(root, "dist", file)));
  return {
    requests: assets.size,
    raw: content.reduce((total, bytes) => total + bytes.byteLength, 0),
    gzip: content.reduce(
      (total, bytes) => total + gzipSync(bytes, { level: 9, mtime: 0 }).byteLength,
      0,
    ),
  };
}

export function loadProfile(root = dirname(fileURLToPath(import.meta.url))) {
  const manifest = readManifest(root);
  const shellKey = findEntry(manifest, (entry) => entry.isEntry === true);
  const dynamic = manifest[shellKey].dynamicImports ?? [];
  const mapKey = findEntry(
    manifest,
    (entry, key) => dynamic.includes(key) && entry.name === "Map",
  );
  const fallbackKey = findEntry(
    manifest,
    (entry) => entry.src === "src/components/map/Fallback.tsx",
  );
  const spaceKey = findEntry(
    manifest,
    (entry) => entry.src === "src/components/map/Space.tsx",
  );
  const nonMapKeys = dynamic.filter((key) => key !== mapKey);
  const shell = outputAssets(manifest, staticClosure(manifest, [shellKey]));
  const mapAll = outputAssets(manifest, staticClosure(manifest, [mapKey]));
  const map = subtractAssets(mapAll, shell);
  const loadedMap = new Set([...shell, ...map]);
  const twoD = subtractAssets(
    outputAssets(manifest, staticClosure(manifest, [fallbackKey])),
    loadedMap,
  );
  const threeD = subtractAssets(
    outputAssets(manifest, staticClosure(manifest, [spaceKey])),
    loadedMap,
  );
  return {
    root,
    manifest,
    keys: { shellKey, mapKey, fallbackKey, spaceKey, nonMapKeys },
    assets: { shell, map, twoD, threeD },
    sizes: {
      shell: sizeProfile(root, shell),
      map: sizeProfile(root, map),
      twoD: sizeProfile(root, twoD),
      threeD: sizeProfile(root, threeD),
    },
  };
}

export function routeAssets(profile, keys) {
  return outputAssets(profile.manifest, staticClosure(profile.manifest, keys));
}
