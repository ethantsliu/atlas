import { isRecord, isString } from "./guards";
import { basePath } from "./paths";
import {
  cloudPath,
  digestOf,
  type CloudManifest,
  type CloudRange,
  type CloudRelation,
} from "./cloud";

function hexAt(bytes: ArrayBuffer, offset: number): string {
  return Array.from(new Uint8Array(bytes, offset, 32), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function parseAnchors(value: unknown, manifest: CloudManifest): string[] {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    value.model !== "all-minilm" ||
    value.model_digest !== manifest.model_digest ||
    value.anchor_sha256 !== manifest.anchor_sha256 ||
    value.count !== manifest.anchor_count ||
    !Array.isArray(value.ids) ||
    value.ids.length !== value.count ||
    !value.ids.every(
      (id) => isString(id) && id.length > 0 && id.length <= 240 && !/\s/.test(id),
    ) ||
    new Set(value.ids).size !== value.ids.length
  ) {
    throw new Error("Paper relation anchors have an invalid shape");
  }
  return value.ids;
}

function parseRoutes(
  bytes: ArrayBuffer,
  manifest: CloudManifest,
  range: CloudRange,
  index: number,
  ids: string[],
): CloudRelation {
  const view = new DataView(bytes);
  const magic = new TextDecoder().decode(new Uint8Array(bytes, 0, 8));
  const count = view.getUint32(8, true);
  const neighbors = view.getUint16(12, true);
  const anchors = view.getUint16(14, true);
  const local = index - range.start;
  if (
    magic !== "ATLASRT1" ||
    count !== range.count ||
    neighbors !== 8 ||
    neighbors !== manifest.neighbor_count ||
    anchors !== manifest.anchor_count ||
    ids.length !== anchors ||
    local < 0 ||
    local >= count ||
    hexAt(bytes, 16) !== range.row_sha256 ||
    hexAt(bytes, 48) !== range.anchor_sha256 ||
    bytes.byteLength !== 80 + count * neighbors * 4
  ) {
    throw new Error("Paper relation routes have an invalid shape");
  }
  const rows: { id: string; ordinal: number; quantized: number; score: number }[] = [];
  const seen = new Set<number>();
  let offset = 80 + local * neighbors * 4;
  for (let slot = 0; slot < neighbors; slot += 1) {
    const ordinal = view.getUint16(offset, true);
    const quantized = view.getUint16(offset + 2, true);
    offset += 4;
    if (ordinal >= anchors || seen.has(ordinal)) {
      throw new Error("Paper relation routes have an invalid shape");
    }
    seen.add(ordinal);
    rows.push({
      id: ids[ordinal],
      ordinal,
      quantized,
      score: (quantized * 2) / 65_535 - 1,
    });
  }
  const ordered = [...rows].sort(
    (left, right) => right.quantized - left.quantized || left.ordinal - right.ordinal,
  );
  if (ordered.some((row, slot) => row !== rows[slot])) {
    throw new Error("Paper relation routes have an invalid shape");
  }
  return { neighbors: rows.map(({ id, score }) => ({ id, score })) };
}

export async function fetchRelation(
  manifest: CloudManifest,
  range: CloudRange,
  index: number,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
  base?: string,
): Promise<CloudRelation> {
  if (!manifest.anchors || !range.routes) {
    throw new Error("Paper relations are unavailable for this corpus");
  }
  const [anchorResponse, routeResponse] = await Promise.all(
    [manifest.anchors, range.routes].map((asset) =>
      fetcher(basePath(cloudPath(asset), base), {
        signal,
        cache: "force-cache",
      }),
    ),
  );
  if (!anchorResponse.ok || !routeResponse.ok) {
    throw new Error("Paper relation request failed");
  }
  const [anchorBytes, routeBytes] = await Promise.all([
    anchorResponse.arrayBuffer(),
    routeResponse.arrayBuffer(),
  ]);
  if (
    anchorBytes.byteLength !== manifest.anchors.bytes ||
    routeBytes.byteLength !== range.routes.bytes ||
    (await digestOf(anchorBytes)) !== manifest.anchors.sha256 ||
    (await digestOf(routeBytes)) !== range.routes.sha256
  ) {
    throw new Error("Paper relations do not match their index");
  }
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder().decode(anchorBytes));
  } catch {
    throw new Error("Paper relation anchors have an invalid shape");
  }
  return parseRoutes(routeBytes, manifest, range, index, parseAnchors(value, manifest));
}
