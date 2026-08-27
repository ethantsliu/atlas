import { isRecord, isString } from "./guards";
import type { CloudPaper, CloudRange } from "./cloud";

const PUBLISHED = /^\d{4}-\d{2}-\d{2}(?:T[^\s]+)?$/;
const SCOPE_NAMES = ["likely", "possible", "outside"] as const;
const SCOPES = new Set<string>(SCOPE_NAMES);

async function rowHash(ids: string[]): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(ids));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export async function parseRows(
  bytes: ArrayBuffer,
  range: CloudRange,
  scopes?: Uint8Array,
): Promise<CloudPaper[]> {
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error("Paper metadata has an invalid shape");
  }
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    value.month !== range.month ||
    value.count !== range.count ||
    !Array.isArray(value.papers) ||
    value.papers.length !== range.count ||
    (scopes && scopes.length !== range.count)
  ) {
    throw new Error("Paper metadata has an invalid shape");
  }
  const papers = value.papers.map((row, index) => {
    if (
      !Array.isArray(row) ||
      row.length !== 5 ||
      !row.every(isString) ||
      !row[0] ||
      !row[1].trim() ||
      !/^https:\/\/arxiv\.org\/abs\//.test(row[2]) ||
      !PUBLISHED.test(row[3]) ||
      !SCOPES.has(row[4]) ||
      (scopes && SCOPE_NAMES[scopes[index]] !== row[4])
    ) {
      throw new Error("Paper metadata has an invalid shape");
    }
    return {
      id: row[0],
      title: row[1],
      url: row[2],
      published: row[3],
      scope: row[4] as CloudPaper["scope"],
    };
  });
  if (
    range.row_sha256 &&
    (await rowHash(papers.map(({ id }) => id))) !== range.row_sha256
  ) {
    throw new Error("Paper metadata row identity does not match its index");
  }
  return papers;
}
