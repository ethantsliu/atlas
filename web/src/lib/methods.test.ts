import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { readMethodCandidate } from "./methoddetail";
import { MethodLru, requestMethodAsset, requestMethodBytes } from "./methodload";
import { MethodsClient } from "./methodroute";
import {
  METHOD_CAPS,
  readMethodIndex,
  readMethodSummary,
  type MethodAsset,
} from "./methods";
import { methodSummaryText, normalizeMethodQuery, readMethodTop } from "./methodview";

const encoder = new TextEncoder();
const corpus = "c".repeat(64);

function rawRow(id: string, label: string, support: number) {
  return {
    id: `method-candidate:${id.repeat(64)}`,
    status: "corpus-extracted-candidate",
    label,
    kind: "method-noun",
    head: "algorithm",
    support_count: support,
    mention_count: support + 2,
    first_year: "2020",
    last_year: "2026",
    scope_counts: { likely: support, possible: 0, outside: 0 },
  };
}

function fullRow(row: ReturnType<typeof rawRow>) {
  return {
    ...row,
    evidence: [
      {
        source_id: "arxiv:2401.00001",
        field: "abstract",
        span: [4, 12],
        text: row.label,
        published: "2024-01-02T00:00:00Z",
        primary_category: "cs.LG",
      },
    ],
  };
}

function hash(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function responseBody(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
}

function rawAsset(asset: MethodAsset) {
  return {
    path: asset.path,
    encoding: asset.encoding,
    sha256: asset.sha256,
    bytes: asset.bytes,
    row_count: asset.rowCount,
  };
}

function indexValue(
  families: unknown[],
  summary: MethodAsset,
  top: MethodAsset,
  search: MethodAsset,
  details: MethodAsset,
) {
  return {
    schema_version: 1,
    generator_version: "methods-browser-1",
    status: "corpus-extracted-candidates",
    tier: "full-evidence",
    corpus: { manifest_sha256: corpus, source_count: 3_148_342, month_count: 444 },
    extraction: {
      normalization_version: "method-phrase-1",
      minimum_support: 3,
      maximum_evidence: 6,
      candidate_limit: null,
    },
    coverage: {
      scanned_papers: 3_148_342,
      scanned_abstracts: 3_148_342,
      quarantined_abstracts: 7,
      extracted_mentions: 20,
      distinct_extracted_candidates: 3,
      qualified_candidates: 2,
    },
    curated_families: families,
    assets: {
      summary: rawAsset(summary),
      top: rawAsset(top),
      search: rawAsset(search),
      details: rawAsset(details),
      download: {
        url: "https://github.com/ethantsliu/atlas/releases/download/methods-v1/candidates.jsonl.gz",
        encoding: "jsonl+gzip",
        sha256: "d".repeat(64),
        bytes: 500,
        row_count: 2,
      },
    },
    notice: "Open-vocabulary candidates are not reviewed techniques.",
  };
}

function packageFixture(adaptive = false) {
  const files = new Map<string, Uint8Array>();
  const store = (stem: string, body: unknown, rowCount: number): MethodAsset => {
    const bytes = encoder.encode(JSON.stringify(body));
    const sha256 = hash(bytes);
    const path = `${stem}-${sha256.slice(0, 16)}.json`;
    files.set(`/atlas/data/methods/${path}`, bytes);
    return { path, encoding: "json", sha256, bytes: bytes.byteLength, rowCount };
  };
  const families = Array.from({ length: 24 }, (_, position) => ({
    id: `family-${position.toString().padStart(2, "0")}`,
    status: "curated-family",
    label: `family ${position}`,
    paper_count: position,
  }));
  const first = rawRow("a", "sparse routing algorithm", 8);
  const second = rawRow("b", "spatial sampling algorithm", 5);
  const rows = [first, second];
  const summaryBody = {
    schema_version: 1,
    corpus_manifest_sha256: corpus,
    qualified_candidates: 2,
    distinct_extracted_candidates: 3,
    curated_families: families,
    by_kind: [
      { kind: "method-noun", count: 2 },
      { kind: "process-technique", count: 0 },
    ],
    by_scope: [
      { scope: "likely", count: 13 },
      { scope: "possible", count: 0 },
      { scope: "outside", count: 0 },
    ],
    by_support: [
      { minimum: 3, maximum: 9, count: 2 },
      { minimum: 10, maximum: 99, count: 0 },
      { minimum: 100, maximum: 999, count: 0 },
      { minimum: 1_000, maximum: 9_999, count: 0 },
      { minimum: 10_000, maximum: null, count: 0 },
    ],
    by_first_year: [{ year: "2020", count: 2 }],
  };
  const topBody = {
    schema_version: 1,
    corpus_manifest_sha256: corpus,
    order: "support-desc-label-asc-head-asc",
    rows,
  };
  const searchLeafBody = {
    schema_version: 1,
    corpus_manifest_sha256: corpus,
    prefix: "spa",
    hash_prefix: "",
    rows,
  };
  const searchLeaf = {
    ...rawAsset(store("search-spa", searchLeafBody, 2)),
    kind: "leaf",
    route_mode: "hash",
    prefix: "spa",
  };
  const plainSearchLeaf = { ...searchLeaf };
  delete (plainSearchLeaf as Partial<typeof searchLeaf>).route_mode;
  const detailA = {
    ...rawAsset(
      store(
        "detail-aa",
        {
          schema_version: 1,
          corpus_manifest_sha256: corpus,
          prefix: "aa",
          rows: [fullRow(first)],
        },
        1,
      ),
    ),
    kind: "leaf",
    prefix: "aa",
  };
  const detailB = {
    ...rawAsset(
      store(
        "detail-bb",
        {
          schema_version: 1,
          corpus_manifest_sha256: corpus,
          prefix: "bb",
          rows: [fullRow(second)],
        },
        1,
      ),
    ),
    kind: "leaf",
    prefix: "bb",
  };
  const searchRoot = adaptive
    ? {
        ...rawAsset(
          store(
            "search-route",
            {
              schema_version: 1,
              corpus_manifest_sha256: corpus,
              route_kind: "search",
              route_mode: "word",
              prefix: "s",
              row_count: 2,
              shards: [plainSearchLeaf],
            },
            2,
          ),
        ),
        kind: "router",
        route_mode: "word",
        prefix: "s",
      }
    : searchLeaf;
  const detailRoot = adaptive
    ? {
        ...rawAsset(
          store(
            "detail-route",
            {
              schema_version: 1,
              corpus_manifest_sha256: corpus,
              route_kind: "detail",
              route_mode: "hash",
              prefix: "a",
              row_count: 1,
              shards: [detailA],
            },
            1,
          ),
        ),
        kind: "router",
        route_mode: "hash",
        prefix: "a",
      }
    : detailA;
  const summary = store("summary", summaryBody, 1);
  const top = store("top", topBody, 2);
  const search = store(
    "search",
    {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      normalization: "nfkc-lower-alnum-space-1",
      minimum_query_length: 3,
      row_count: 2,
      shards: [searchRoot],
    },
    2,
  );
  const details = store(
    "details",
    {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      prefix_bits: 8,
      row_count: 2,
      shards: [detailRoot, detailB],
    },
    2,
  );
  const indexBody = indexValue(families, summary, top, search, details);
  files.set(
    "/atlas/data/methods/index.json",
    encoder.encode(JSON.stringify(indexBody)),
  );
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const body = files.get(String(input));
    return body
      ? new Response(responseBody(body), {
          headers: { "content-length": String(body.byteLength) },
        })
      : new Response("missing", { status: 404 });
  }) as unknown as typeof fetch;
  return { files, fetcher, indexBody, summaryBody, topBody, rows };
}

function catalogNodes(
  store: (stem: string, body: unknown, rowCount: number) => MethodAsset,
  adaptive: boolean,
) {
  const rows = [
    rawRow("a", "sparse routing algorithm", 8),
    rawRow("b", "spatial sampling algorithm", 5),
  ];
  const identities = rows.map((row, ordinal) => ({
    ordinal,
    full_row_sha256: hash(encoder.encode(JSON.stringify(fullRow(row)))),
    ...row,
  }));
  const full = "d".repeat(64);
  const detailLeaf = {
    ...rawAsset(
      store(
        "detail-00000000",
        {
          schema_version: 1,
          corpus_manifest_sha256: corpus,
          full_asset_sha256: full,
          route_kind: "detail",
          route_mode: "ordinal",
          prefix: "00000000",
          start_ordinal: 0,
          end_ordinal: 1,
          columns: [
            "ordinal",
            "full_row_sha256",
            "id",
            "status",
            "label",
            "kind",
            "head",
            "support_count",
            "mention_count",
            "first_year",
            "last_year",
            "scope_counts",
          ],
          rows: identities.map((row) => [
            row.ordinal,
            row.full_row_sha256,
            row.id,
            row.status,
            row.label,
            row.kind,
            row.head,
            row.support_count,
            row.mention_count,
            row.first_year,
            row.last_year,
            row.scope_counts,
          ]),
        },
        2,
      ),
    ),
    kind: "leaf",
    route_mode: "ordinal",
    prefix: "00000000",
    start_ordinal: 0,
    end_ordinal: 1,
  };
  const searchLeaf = {
    ...rawAsset(
      store(
        "search-spa",
        {
          schema_version: 1,
          corpus_manifest_sha256: corpus,
          full_asset_sha256: full,
          prefix: "spa",
          hash_prefix: "",
          ordinals: [0, 1],
        },
        2,
      ),
    ),
    kind: "leaf",
    route_mode: "hash",
    prefix: "spa",
  };
  const wordSearchLeaf = { ...searchLeaf };
  delete (wordSearchLeaf as Partial<typeof searchLeaf>).route_mode;
  const detailNode = adaptive
    ? {
        ...rawAsset(
          store(
            "detail-route",
            {
              schema_version: 1,
              corpus_manifest_sha256: corpus,
              full_asset_sha256: full,
              route_kind: "detail",
              route_mode: "ordinal",
              prefix: "00000000",
              start_ordinal: 0,
              end_ordinal: 1,
              row_count: 2,
              shards: [detailLeaf],
            },
            2,
          ),
        ),
        kind: "router",
        route_mode: "ordinal",
        prefix: "00000000",
        start_ordinal: 0,
        end_ordinal: 1,
      }
    : detailLeaf;
  const searchNode = adaptive
    ? {
        ...rawAsset(
          store(
            "search-route",
            {
              schema_version: 1,
              corpus_manifest_sha256: corpus,
              full_asset_sha256: full,
              route_kind: "search",
              route_mode: "word",
              prefix: "s",
              row_count: 2,
              shards: [wordSearchLeaf],
            },
            2,
          ),
        ),
        kind: "router",
        route_mode: "word",
        prefix: "s",
      }
    : searchLeaf;
  return { rows, identities, full, searchNode, detailNode };
}

function catalogFixture(adaptive = false) {
  const files = new Map<string, Uint8Array>();
  const store = (stem: string, body: unknown, rowCount: number): MethodAsset => {
    const bytes = encoder.encode(JSON.stringify(body));
    const sha256 = hash(bytes);
    const path = `${stem}-${sha256.slice(0, 16)}.json`;
    files.set(`/atlas/data/methods/${path}`, bytes);
    return { path, encoding: "json", sha256, bytes: bytes.byteLength, rowCount };
  };
  const families = Array.from({ length: 24 }, (_, position) => ({
    id: `family-${position.toString().padStart(2, "0")}`,
    status: "curated-family",
    label: `family ${position}`,
    paper_count: position,
  }));
  const { identities, full, searchNode, detailNode } = catalogNodes(store, adaptive);
  const summary = store(
    "summary",
    {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      qualified_candidates: 2,
      distinct_extracted_candidates: 3,
      curated_families: families,
      by_kind: [
        { kind: "method-noun", count: 2 },
        { kind: "process-technique", count: 0 },
      ],
      by_scope: [
        { scope: "likely", count: 13 },
        { scope: "possible", count: 0 },
        { scope: "outside", count: 0 },
      ],
      by_support: [
        { minimum: 3, maximum: 9, count: 2 },
        { minimum: 10, maximum: 99, count: 0 },
        { minimum: 100, maximum: 999, count: 0 },
        { minimum: 1_000, maximum: 9_999, count: 0 },
        { minimum: 10_000, maximum: null, count: 0 },
      ],
      by_first_year: [{ year: "2020", count: 2 }],
    },
    1,
  );
  const top = store(
    "top",
    {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      full_asset_sha256: full,
      order: "support-desc-label-asc-head-asc",
      rows: identities,
    },
    2,
  );
  const search = store(
    "search",
    {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      full_asset_sha256: full,
      normalization: "nfkc-lower-alnum-space-1",
      minimum_query_length: 3,
      row_count: 2,
      shards: [searchNode],
    },
    2,
  );
  const details = store(
    "details",
    {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      full_asset_sha256: full,
      route_kind: "detail",
      route_mode: "ordinal",
      start_ordinal: 0,
      end_ordinal: 1,
      row_count: 2,
      shards: [detailNode],
    },
    2,
  );
  const indexBody = {
    ...indexValue(families, summary, top, search, details),
    tier: "catalog-only",
    notice:
      "Open-vocabulary candidates are not reviewed techniques. Evidence spans are available only in the immutable full release download.",
  };
  files.set(
    "/atlas/data/methods/index.json",
    encoder.encode(JSON.stringify(indexBody)),
  );
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const body = files.get(String(input));
    return body
      ? new Response(responseBody(body), {
          headers: { "content-length": String(body.byteLength) },
        })
      : new Response("missing", { status: 404 });
  }) as unknown as typeof fetch;
  return { fetcher, indexBody, identities };
}

describe("method browser contracts", () => {
  it("loads only index, summary, and top until search or evidence is requested", async () => {
    const fixture = packageFixture(true);
    const client = new MethodsClient(fixture.fetcher, "/atlas/");
    const signal = new AbortController().signal;
    const overview = await client.load(signal);

    expect(overview.summary.qualifiedCandidates).toBe(2);
    expect(fixture.fetcher).toHaveBeenCalledTimes(3);
    expect(
      (fixture.fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls.map(([url]) =>
        String(url),
      ),
    ).not.toEqual(expect.arrayContaining([expect.stringContaining("search-")]));

    await expect(client.search("ＳＰＡ", signal)).resolves.toHaveLength(2);
    await expect(client.detail(overview.top[0], signal)).resolves.toMatchObject({
      availability: "inline",
      candidate: {
        label: "sparse routing algorithm",
        evidence: [{ sourceId: "arxiv:2401.00001" }],
      },
    });
  });

  it("hydrates catalog search identities and keeps evidence release-only", async () => {
    const fixture = catalogFixture(true);
    const client = new MethodsClient(fixture.fetcher, "/atlas/");
    const signal = new AbortController().signal;
    const overview = await client.load(signal);

    expect(overview.index.tier).toBe("catalog-only");
    expect(fixture.fetcher).toHaveBeenCalledTimes(3);
    await expect(client.search("spa", signal)).resolves.toMatchObject([
      { ordinal: 0, label: "sparse routing algorithm" },
      { ordinal: 1, label: "spatial sampling algorithm" },
    ]);
    await expect(client.detail(overview.top[0], signal)).resolves.toMatchObject({
      availability: "release-only",
      candidate: { ordinal: 0 },
      download: { sha256: "d".repeat(64) },
    });
    expect(
      (fixture.fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls.some(
        ([url]) => String(url).endsWith(".jsonl.gz"),
      ),
    ).toBe(false);
  });

  it("rejects catalog packages without full-release binding or ordinal order", () => {
    const fixture = catalogFixture();
    const missingNotice = { ...fixture.indexBody, notice: "Candidates only." };
    expect(readMethodIndex(missingNotice)).toBeNull();
    const index = readMethodIndex(fixture.indexBody)!;
    const top = {
      schema_version: 1,
      corpus_manifest_sha256: corpus,
      full_asset_sha256: "e".repeat(64),
      order: "support-desc-label-asc-head-asc",
      rows: fixture.identities,
    };
    expect(readMethodTop(top, index)).toBeNull();
    expect(
      readMethodTop(
        {
          ...top,
          full_asset_sha256: "d".repeat(64),
          rows: [fixture.identities[1], fixture.identities[0]],
        },
        index,
      ),
    ).toBeNull();
  });

  it("rejects wrong status, row counts, order, scope sums, and evidence order", () => {
    const fixture = packageFixture();
    const index = readMethodIndex(fixture.indexBody)!;
    expect(index).not.toBeNull();
    expect(
      readMethodIndex({ ...fixture.indexBody, status: "reviewed-techniques" }),
    ).toBeNull();
    const addressed = structuredClone(fixture.indexBody);
    addressed.assets.download.url = `https://github.com/ethantsliu/atlas/releases/download/methods-v1/candidates-${"e".repeat(64)}.jsonl.gz`;
    expect(readMethodIndex(addressed)).not.toBeNull();
    addressed.assets.download.url += "?mutable=1";
    expect(readMethodIndex(addressed)).toBeNull();
    expect(
      readMethodTop({ ...fixture.topBody, rows: [...fixture.rows].reverse() }, index),
    ).toBeNull();
    expect(
      readMethodTop(
        {
          ...fixture.topBody,
          rows: [
            {
              ...fixture.rows[0],
              scope_counts: { likely: 1, possible: 0, outside: 0 },
            },
            fixture.rows[1],
          ],
        },
        index,
      ),
    ).toBeNull();
    expect(
      readMethodSummary({ ...fixture.summaryBody, qualified_candidates: 3 }, index),
    ).toBeNull();

    const candidate = fullRow(fixture.rows[0]);
    candidate.evidence.push({
      ...candidate.evidence[0],
      source_id: "arxiv:2301.00001",
    });
    expect(readMethodCandidate(candidate, index)).toBeNull();
  });

  it("enforces body caps and immutable descriptor hashes before parsing", async () => {
    const oversized = new Response("{}", {
      headers: { "content-length": String(METHOD_CAPS.index + 1) },
    });
    await expect(
      requestMethodBytes(
        "index.json",
        METHOD_CAPS.index,
        new AbortController().signal,
        vi.fn(async () => oversized) as unknown as typeof fetch,
        "/atlas/",
        "no-cache",
      ),
    ).rejects.toThrow("byte cap");

    const body = encoder.encode("{}\n");
    await expect(
      requestMethodAsset(
        {
          path: `summary-${"f".repeat(16)}.json`,
          encoding: "json",
          sha256: "f".repeat(64),
          bytes: body.byteLength,
          rowCount: 1,
        },
        METHOD_CAPS.summary,
        new AbortController().signal,
        vi.fn(async () => new Response(responseBody(body))) as unknown as typeof fetch,
        "/atlas/",
      ),
    ).rejects.toThrow("descriptor");
  });

  it("bounds and refreshes the decoded search-leaf cache", () => {
    const cache = new MethodLru<number>(4, 10);
    cache.set("a", 1, 2);
    cache.set("b", 2, 2);
    cache.set("c", 3, 2);
    cache.set("d", 4, 2);
    expect(cache.get("a")).toBe(1);
    cache.set("e", 5, 2);

    expect(cache.size).toBe(4);
    expect(cache.get("b")).toBeUndefined();
    expect(cache.get("a")).toBe(1);
    cache.set("too-large", 6, 11);
    expect(cache.size).toBe(4);
  });

  it("forwards cancellation to every lazy request", async () => {
    const controller = new AbortController();
    let observed: AbortSignal | null = null;
    const fetcher = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          observed = init?.signal as AbortSignal;
          observed.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        }),
    ) as unknown as typeof fetch;
    const pending = requestMethodBytes(
      "index.json",
      METHOD_CAPS.index,
      controller.signal,
      fetcher,
      "/atlas/",
      "no-cache",
    );
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(observed).toBe(controller.signal);
  });

  it("normalizes search prefixes and reports only corpus frequency", () => {
    const fixture = packageFixture();
    const index = readMethodIndex(fixture.indexBody)!;
    const summary = readMethodSummary(fixture.summaryBody, index)!;

    expect(normalizeMethodQuery("  Ｓparse—Routing! ")).toBe("sparse routing");
    expect(methodSummaryText(summary)).toBe(
      "3,148,342 abstracts scanned · 3 distinct phrases · 2 appearing in at least 3 papers.",
    );
  });
});
