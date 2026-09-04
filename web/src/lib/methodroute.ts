import {
  METHOD_CAPS,
  methodOrder,
  readMethodIndex,
  readMethodSummary,
  type MethodCandidate,
  type MethodIdentity,
  type MethodIndex,
  type MethodOverview,
  type MethodRow,
} from "./methods";
import { isMethodIdentity, normalizeMethodQuery, readMethodTop } from "./methodview";
import { readIdentityRows, readMethodDetails } from "./methoddetail";
import {
  decodeMethodJson,
  MethodLru,
  requestMethodAsset,
  requestMethodBytes,
} from "./methodload";
import {
  readDetailRoot,
  readRouter,
  readSearchLeaf,
  readSearchRoot,
  type MethodNode,
  type MethodRoot,
  type MethodRoute,
  type SearchLeaf,
} from "./methodtree";

const SEARCH_LIMIT = 3;
const ROUTE_LIMIT = 32;
const RESULT_LIMIT = 40;

export type MethodDetail =
  | { availability: "inline"; candidate: MethodCandidate }
  | {
      availability: "release-only";
      candidate: MethodIdentity;
      download: MethodIndex["download"];
    };

function routeWords(query: string): string[] {
  return [
    ...new Set(
      normalizeMethodQuery(query)
        .split(" ")
        .filter((word) => word.length >= 3),
    ),
  ].slice(0, SEARCH_LIMIT);
}

function relevantWord(node: MethodNode, word: string): boolean {
  return word.startsWith(node.prefix) || node.prefix.startsWith(word);
}

function intersect(values: readonly number[][]): number[] {
  const [first = [], ...rest] = values;
  return first.filter((ordinal) => rest.every((items) => items.includes(ordinal)));
}

export class MethodsClient {
  private index: MethodIndex | null = null;
  private searchIndex: MethodRoot | null = null;
  private detailIndex: MethodRoot | null = null;
  private readonly searches = new MethodLru<SearchLeaf>(4, 1024 * 1024);
  private readonly details = new MethodLru<MethodCandidate[] | MethodIdentity[]>(
    2,
    256 * 1024,
  );

  constructor(
    private readonly fetcher: typeof fetch = fetch,
    private readonly base: string = import.meta.env.BASE_URL,
  ) {}

  async load(signal: AbortSignal): Promise<MethodOverview> {
    const bytes = await requestMethodBytes(
      "index.json",
      METHOD_CAPS.index,
      signal,
      this.fetcher,
      this.base,
      "no-cache",
    );
    const index = readMethodIndex(decodeMethodJson(bytes));
    if (!index) throw new Error("Method index is invalid");
    this.index = index;
    const [summaryValue, topValue] = await Promise.all([
      requestMethodAsset(
        index.summary,
        METHOD_CAPS.summary,
        signal,
        this.fetcher,
        this.base,
      ),
      requestMethodAsset(index.top, METHOD_CAPS.top, signal, this.fetcher, this.base),
    ]);
    const summary = readMethodSummary(summaryValue, index);
    const top = readMethodTop(topValue, index);
    if (!summary || !top) throw new Error("Method overview is invalid");
    return { index, summary, top };
  }

  private required(): MethodIndex {
    if (!this.index) throw new Error("Method index has not loaded");
    return this.index;
  }

  private async root(route: MethodRoute, signal: AbortSignal): Promise<MethodRoot> {
    const index = this.required();
    if (route === "search" && this.searchIndex) return this.searchIndex;
    if (route === "detail" && this.detailIndex) return this.detailIndex;
    const asset = route === "search" ? index.search : index.details;
    const value = await requestMethodAsset(
      asset,
      METHOD_CAPS.router,
      signal,
      this.fetcher,
      this.base,
    );
    const parsed =
      route === "search" ? readSearchRoot(value, index) : readDetailRoot(value, index);
    if (!parsed) throw new Error(`Method ${route} index is invalid`);
    if (route === "search") this.searchIndex = parsed;
    else this.detailIndex = parsed;
    return parsed;
  }

  private async router(
    node: MethodNode,
    route: MethodRoute,
    signal: AbortSignal,
  ): Promise<MethodNode[]> {
    const value = await requestMethodAsset(
      node,
      METHOD_CAPS.router,
      signal,
      this.fetcher,
      this.base,
    );
    const parsed = readRouter(value, this.required(), node, route);
    if (!parsed) throw new Error("Method routing node is invalid");
    return parsed;
  }

  private async searchNode(
    node: MethodNode,
    word: string,
    signal: AbortSignal,
    remaining: { leaves: number; routes: number },
    seen: Set<string>,
  ): Promise<SearchLeaf[]> {
    if (
      remaining.leaves <= 0 ||
      remaining.routes <= 0 ||
      seen.has(node.path) ||
      !relevantWord(node, word)
    ) {
      return [];
    }
    seen.add(node.path);
    if (node.kind === "leaf") {
      remaining.leaves -= 1;
      const cached = this.searches.get(node.path);
      if (cached) return [cached];
      const value = await requestMethodAsset(
        node,
        METHOD_CAPS.search,
        signal,
        this.fetcher,
        this.base,
      );
      const leaf = readSearchLeaf(value, this.required(), node);
      if (!leaf) throw new Error("Method search leaf is invalid");
      this.searches.set(node.path, leaf, node.bytes);
      return [leaf];
    }
    remaining.routes -= 1;
    const children = await this.router(node, "search", signal);
    const relevant = children.filter((child) =>
      node.routeMode === "hash" ? true : relevantWord(child, word),
    );
    const leaves: SearchLeaf[] = [];
    for (const child of relevant) {
      leaves.push(...(await this.searchNode(child, word, signal, remaining, seen)));
      if (remaining.leaves <= 0) break;
    }
    return leaves;
  }

  private async searchWord(word: string, allowance: number, signal: AbortSignal) {
    const root = await this.root("search", signal);
    const remaining = { leaves: allowance, routes: ROUTE_LIMIT };
    const leaves: SearchLeaf[] = [];
    for (const node of root.shards) {
      leaves.push(
        ...(await this.searchNode(node, word, signal, remaining, new Set<string>())),
      );
      if (remaining.leaves <= 0) break;
    }
    return leaves;
  }

  private async identity(
    ordinal: number,
    signal: AbortSignal,
  ): Promise<MethodIdentity> {
    const index = this.required();
    const root = await this.root("detail", signal);
    let nodes = root.shards;
    const seen = new Set<string>();
    for (let depth = 0; depth < ROUTE_LIMIT; depth += 1) {
      const node = nodes.find(
        (item) =>
          (item.startOrdinal ?? Number.MAX_SAFE_INTEGER) <= ordinal &&
          (item.endOrdinal ?? -1) >= ordinal,
      );
      if (!node || seen.has(node.path)) break;
      seen.add(node.path);
      if (node.kind === "router") {
        nodes = await this.router(node, "detail", signal);
        continue;
      }
      let rows = this.details.get(node.path) as MethodIdentity[] | undefined;
      if (!rows) {
        const value = await requestMethodAsset(
          node,
          METHOD_CAPS.detail,
          signal,
          this.fetcher,
          this.base,
        );
        rows =
          readIdentityRows(
            value,
            index,
            node.prefix,
            node.startOrdinal ?? -1,
            node.endOrdinal ?? -1,
            node.rowCount,
          ) ?? undefined;
        if (!rows) throw new Error("Method identity leaf is invalid");
        this.details.set(node.path, rows, node.bytes);
      }
      const match = rows.find((row) => row.ordinal === ordinal);
      if (!match) throw new Error("Method identity is missing");
      return match;
    }
    throw new Error("Method identity route is invalid");
  }

  async search(query: string, signal: AbortSignal): Promise<MethodRow[]> {
    const words = routeWords(query);
    if (!words.length) return [];
    const allowance = words.length === 1 ? SEARCH_LIMIT : 1;
    const groups = [];
    for (const word of words)
      groups.push(await this.searchWord(word, allowance, signal));
    if (this.required().tier === "catalog-only") {
      const ordinals = groups.map((leaves) =>
        [...new Set(leaves.flatMap((leaf) => leaf.ordinals ?? []))].sort(
          (left, right) => left - right,
        ),
      );
      const matches = intersect(ordinals).slice(0, RESULT_LIMIT);
      const rows = [];
      for (const ordinal of matches) rows.push(await this.identity(ordinal, signal));
      return rows
        .filter((row) =>
          words.every((word) =>
            normalizeMethodQuery(row.label)
              .split(" ")
              .some((labelWord) => labelWord.startsWith(word)),
          ),
        )
        .sort(methodOrder)
        .slice(0, RESULT_LIMIT);
    }
    const sets = groups.map(
      (leaves) =>
        new Map(leaves.flatMap((leaf) => leaf.rows ?? []).map((row) => [row.id, row])),
    );
    const first = sets[0] ?? new Map<string, MethodRow>();
    return [...first.values()]
      .filter((row) => sets.every((set) => set.has(row.id)))
      .sort(methodOrder)
      .slice(0, RESULT_LIMIT);
  }

  private async inline(id: string, signal: AbortSignal): Promise<MethodCandidate> {
    const root = await this.root("detail", signal);
    const digest = id.slice("method-candidate:".length);
    let nodes = root.shards;
    const seen = new Set<string>();
    for (let depth = 0; depth < ROUTE_LIMIT; depth += 1) {
      const node = nodes
        .filter((item) => digest.startsWith(item.prefix))
        .sort((left, right) => right.prefix.length - left.prefix.length)[0];
      if (!node || seen.has(node.path)) break;
      seen.add(node.path);
      if (node.kind === "router") {
        nodes = await this.router(node, "detail", signal);
        continue;
      }
      let rows = this.details.get(node.path) as MethodCandidate[] | undefined;
      if (!rows) {
        const value = await requestMethodAsset(
          node,
          METHOD_CAPS.detail,
          signal,
          this.fetcher,
          this.base,
        );
        rows =
          readMethodDetails(value, this.required(), node.prefix, node.rowCount) ??
          undefined;
        if (!rows) throw new Error("Method detail leaf is invalid");
        this.details.set(node.path, rows, node.bytes);
      }
      const matches = rows.filter((row) => row.id === id);
      if (matches.length !== 1) throw new Error("Method candidate detail is missing");
      return matches[0];
    }
    throw new Error("Method candidate detail route is invalid");
  }

  async detail(row: MethodRow, signal: AbortSignal): Promise<MethodDetail> {
    if (!/^method-candidate:[0-9a-f]{64}$/.test(row.id)) {
      throw new Error("Method candidate ID is invalid");
    }
    const index = this.required();
    if (index.tier === "catalog-only") {
      if (!isMethodIdentity(row))
        throw new Error("Method candidate identity is invalid");
      return { availability: "release-only", candidate: row, download: index.download };
    }
    return { availability: "inline", candidate: await this.inline(row.id, signal) };
  }
}
