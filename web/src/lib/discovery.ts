import { hasOnlyKeys, isRecord, isString } from "./guards";
import { basePath } from "./paths";

const ROOT_KEYS = new Set([
  "schema_version",
  "generator_version",
  "status",
  "source",
  "count",
  "review_gate",
  "notice",
  "candidates",
]);
const SOURCE_KEYS = new Set([
  "run_id",
  "artifact_id",
  "artifact_sha256",
  "generator_version",
  "corpus_digest",
  "manifest_sha256",
  "manifest_papers",
  "loaded_papers",
  "skipped_outside",
]);
const GATE_KEYS = new Set(["automatic_promotion", "required_receipt", "note"]);
const ROW_KEYS = new Set(["id", "digest", "review_status", "identity", "support_ids"]);
const IDENTITY_KEYS = new Set(["target", "intervention", "mechanism", "outcome"]);
const SHA256 = /^[0-9a-f]{64}$/;
const IDEA_ID = /^idea:[0-9a-f]{64}$/;
const ARXIV_ID = /^arxiv:(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*\/\d{7})$/;
const REVIEW_NOTE =
  "Promotion requires a declared review receipt bound to the candidate digest; this receipt is not authenticated human proof, and provenance hashes are not related-work evidence.";

export type DiscoveryIdentity = {
  target: string;
  intervention: string;
  mechanism: string;
  outcome: string;
};

export type DiscoveryCandidate = {
  id: string;
  digest: string;
  reviewStatus: "unreviewed";
  identity: DiscoveryIdentity;
  supportIds: string[];
};

export type DiscoveryQueue = {
  source: {
    runId: number;
    artifactId: number;
    artifactSha256: string;
    corpusDigest: string;
    manifestSha256: string;
    manifestPapers: number;
    loadedPapers: number;
    skippedOutside: number;
  };
  notice: string;
  candidates: DiscoveryCandidate[];
};

function exact(value: Record<string, unknown>, keys: ReadonlySet<string>): boolean {
  return hasOnlyKeys(value, keys) && Object.keys(value).length === keys.size;
}

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function nonnegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function readIdentity(value: unknown): DiscoveryIdentity | null {
  if (!isRecord(value) || !exact(value, IDENTITY_KEYS)) return null;
  for (const field of IDENTITY_KEYS) {
    const text = value[field];
    if (!isString(text) || !text || text !== text.trim() || text.length > 240) {
      return null;
    }
  }
  return value as DiscoveryIdentity;
}

function readCandidate(value: unknown): DiscoveryCandidate | null {
  if (!isRecord(value) || !exact(value, ROW_KEYS)) return null;
  const identity = readIdentity(value.identity);
  const supports = value.support_ids;
  if (
    !isString(value.id) ||
    !IDEA_ID.test(value.id) ||
    !isString(value.digest) ||
    !SHA256.test(value.digest) ||
    value.review_status !== "unreviewed" ||
    !identity ||
    !Array.isArray(supports) ||
    supports.length < 2 ||
    supports.length > 12 ||
    !supports.every((id) => isString(id) && ARXIV_ID.test(id)) ||
    supports.some((id, index) => index > 0 && id <= supports[index - 1])
  ) {
    return null;
  }
  return {
    id: value.id,
    digest: value.digest,
    reviewStatus: "unreviewed",
    identity,
    supportIds: supports,
  };
}

export function readDiscoveryQueue(value: unknown): DiscoveryQueue | null {
  if (
    !isRecord(value) ||
    !exact(value, ROOT_KEYS) ||
    value.schema_version !== 1 ||
    value.generator_version !== "discovery-browser-1" ||
    value.status !== "provisional" ||
    !isString(value.notice) ||
    !value.notice.includes("not screened briefs") ||
    !isRecord(value.source) ||
    !exact(value.source, SOURCE_KEYS) ||
    !isRecord(value.review_gate) ||
    !exact(value.review_gate, GATE_KEYS) ||
    value.review_gate.automatic_promotion !== false ||
    value.review_gate.required_receipt !== "declared-human-review" ||
    value.review_gate.note !== REVIEW_NOTE ||
    !Array.isArray(value.candidates) ||
    !positiveInteger(value.count) ||
    value.count !== value.candidates.length ||
    value.count > 48
  ) {
    return null;
  }
  const source = value.source;
  if (
    !positiveInteger(source.run_id) ||
    !positiveInteger(source.artifact_id) ||
    !isString(source.artifact_sha256) ||
    !SHA256.test(source.artifact_sha256) ||
    source.generator_version !== "discover-2" ||
    !isString(source.corpus_digest) ||
    !SHA256.test(source.corpus_digest) ||
    !isString(source.manifest_sha256) ||
    !SHA256.test(source.manifest_sha256) ||
    !positiveInteger(source.manifest_papers) ||
    !positiveInteger(source.loaded_papers) ||
    !nonnegativeInteger(source.skipped_outside) ||
    source.loaded_papers + source.skipped_outside !== source.manifest_papers
  ) {
    return null;
  }
  const candidates = value.candidates.map(readCandidate);
  if (candidates.some((candidate) => candidate === null)) return null;
  const rows = candidates as DiscoveryCandidate[];
  const ids = rows.map((candidate) => candidate.id);
  if (
    new Set(ids).size !== ids.length ||
    ids.some((id, index) => index > 0 && id <= ids[index - 1])
  ) {
    return null;
  }
  return {
    source: {
      runId: source.run_id,
      artifactId: source.artifact_id,
      artifactSha256: source.artifact_sha256,
      corpusDigest: source.corpus_digest,
      manifestSha256: source.manifest_sha256,
      manifestPapers: source.manifest_papers,
      loadedPapers: source.loaded_papers,
      skippedOutside: source.skipped_outside,
    },
    notice: value.notice,
    candidates: rows,
  };
}

export async function fetchDiscoveryQueue(
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
  base: string = import.meta.env.BASE_URL,
): Promise<DiscoveryQueue> {
  const response = await fetcher(basePath("/data/discovery.json", base), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Discovery queue request failed (${response.status})`);
  }
  const queue = readDiscoveryQueue(await response.json());
  if (!queue) throw new Error("Discovery queue response is invalid");
  return queue;
}
