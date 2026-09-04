import { basePath } from "./paths";
import type { MethodAsset } from "./methods";

async function bounded(response: Response, cap: number): Promise<Uint8Array> {
  const header = response.headers.get("content-length");
  if (header && /^\d+$/.test(header) && Number(header) > cap) {
    await response.body?.cancel();
    throw new Error("Method asset exceeds its byte cap");
  }
  if (!response.body) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > cap) throw new Error("Method asset exceeds its byte cap");
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > cap) {
        await reader.cancel();
        throw new Error("Method asset exceeds its byte cap");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

async function digest(bytes: Uint8Array): Promise<string> {
  const source = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
  const value = await globalThis.crypto.subtle.digest("SHA-256", source);
  return [...new Uint8Array(value)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function decodeMethodJson(bytes: Uint8Array): unknown {
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new Error("Method asset is not valid UTF-8 JSON");
  }
}

export async function requestMethodBytes(
  path: string,
  cap: number,
  signal: AbortSignal,
  fetcher: typeof fetch,
  base: string,
  cache: RequestCache,
): Promise<Uint8Array> {
  const response = await fetcher(basePath(`/data/methods/${path}`, base), {
    signal,
    cache,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Method asset request failed (${response.status})`);
  return bounded(response, cap);
}

export async function requestMethodAsset(
  asset: MethodAsset,
  cap: number,
  signal: AbortSignal,
  fetcher: typeof fetch,
  base: string,
): Promise<unknown> {
  if (asset.bytes > cap) throw new Error("Method descriptor exceeds its byte cap");
  const bytes = await requestMethodBytes(
    asset.path,
    Math.min(cap, asset.bytes),
    signal,
    fetcher,
    base,
    "force-cache",
  );
  if (bytes.byteLength !== asset.bytes || (await digest(bytes)) !== asset.sha256) {
    throw new Error("Method asset does not match its descriptor");
  }
  return decodeMethodJson(bytes);
}

export class MethodLru<T> {
  private readonly values = new Map<string, { value: T; bytes: number }>();
  private bytes = 0;

  constructor(
    private readonly entries: number,
    private readonly byteCap: number,
  ) {}

  get(key: string): T | undefined {
    const found = this.values.get(key);
    if (!found) return undefined;
    this.values.delete(key);
    this.values.set(key, found);
    return found.value;
  }

  set(key: string, value: T, bytes: number): void {
    const prior = this.values.get(key);
    if (prior) this.bytes -= prior.bytes;
    this.values.delete(key);
    if (bytes > this.byteCap) return;
    this.values.set(key, { value, bytes });
    this.bytes += bytes;
    while (this.values.size > this.entries || this.bytes > this.byteCap) {
      const oldest = this.values.keys().next().value as string | undefined;
      if (!oldest) break;
      this.bytes -= this.values.get(oldest)?.bytes ?? 0;
      this.values.delete(oldest);
    }
  }

  get size(): number {
    return this.values.size;
  }
}
