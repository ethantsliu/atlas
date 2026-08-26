import { afterEach, describe, expect, it, vi } from "vitest";
import { makeFullReading, makePaper } from "../test/fixtures";
import type { Paper } from "../types";

type Cleanup = void | (() => void);
type EffectSlot = { cleanup: Cleanup; deps: readonly unknown[] };
type PendingEffect = {
  index: number;
  setup: () => Cleanup;
  deps: readonly unknown[];
};

let activeHarness: HookHarness | null = null;

vi.mock("react", () => ({
  useCallback: <Value>(callback: Value) => callback,
  useEffect: (setup: () => Cleanup, deps: readonly unknown[]) => {
    if (!activeHarness) throw new Error("Hook effect rendered outside its harness");
    activeHarness.useEffect(setup, deps);
  },
  useState: <Value>(initial: Value | (() => Value)) => {
    if (!activeHarness) throw new Error("Hook state rendered outside its harness");
    return activeHarness.useState(initial);
  },
}));

import { useFullReading } from "./reading";

class HookHarness {
  private states: unknown[] = [];
  private effects: EffectSlot[] = [];
  private pending: PendingEffect[] = [];
  private stateIndex = 0;
  private effectIndex = 0;
  private dirty = false;

  useState<Value>(
    initial: Value | (() => Value),
  ): [Value, (next: Value | ((value: Value) => Value)) => void] {
    const index = this.stateIndex++;
    if (!(index in this.states)) {
      this.states[index] =
        typeof initial === "function" ? (initial as () => Value)() : initial;
    }
    const update = (next: Value | ((value: Value) => Value)) => {
      const current = this.states[index] as Value;
      const value =
        typeof next === "function" ? (next as (value: Value) => Value)(current) : next;
      if (Object.is(current, value)) return;
      this.states[index] = value;
      this.dirty = true;
    };
    return [this.states[index] as Value, update];
  }

  useEffect(setup: () => Cleanup, deps: readonly unknown[]): void {
    const index = this.effectIndex++;
    const prior = this.effects[index];
    if (
      prior &&
      prior.deps.length === deps.length &&
      prior.deps.every((value, position) => Object.is(value, deps[position]))
    ) {
      return;
    }
    this.pending.push({ index, setup, deps });
  }

  render(paper: Paper): ReturnType<typeof useFullReading> {
    let result: ReturnType<typeof useFullReading>;
    do {
      this.dirty = false;
      this.stateIndex = 0;
      this.effectIndex = 0;
      this.pending = [];
      activeHarness = this;
      try {
        result = useFullReading(paper);
      } finally {
        activeHarness = null;
      }
      this.flushEffects();
    } while (this.dirty);
    return result!;
  }

  unmount(): void {
    this.effects.forEach((effect) => effect.cleanup?.());
    this.effects = [];
  }

  private flushEffects(): void {
    this.pending.forEach(({ index, setup, deps }) => {
      this.effects[index]?.cleanup?.();
      this.effects[index] = { cleanup: setup(), deps };
    });
    this.pending = [];
  }
}

type Deferred<Value> = {
  promise: Promise<Value>;
  resolve: (value: Value) => void;
};

function deferred<Value>(): Deferred<Value> {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function response(
  payload: unknown,
  options: { ok?: boolean; status?: number } = {},
): Response {
  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: async () => payload,
  } as Response;
}

function loadedPaper(stableId: string, path: string): Paper {
  return makePaper({
    stable_id: stableId,
    reading_depth: "verified",
    full_reading_path: path,
  });
}

async function flushPromises(): Promise<void> {
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
}

afterEach(() => {
  activeHarness = null;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useFullReading", () => {
  it("aborts A and suppresses its stale result after rerendering with B", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    const signals: AbortSignal[] = [];
    const fetcher = vi.fn((_path: string, init?: RequestInit) => {
      signals.push(init?.signal as AbortSignal);
      return signals.length === 1 ? first.promise : second.promise;
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);

    const paperA = loadedPaper("arxiv:0001.00001", "/reading-a.json");
    const paperB = loadedPaper("arxiv:0002.00002", "/reading-b.json");
    const readingA = makeFullReading({ stable_id: paperA.stable_id });
    const readingB = makeFullReading({ stable_id: paperB.stable_id });
    const harness = new HookHarness();

    expect(harness.render(paperA).state.status).toBe("loading");
    expect(harness.render(paperB).state.status).toBe("loading");
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);

    second.resolve(response(readingB));
    await flushPromises();
    expect(harness.render(paperB).state).toMatchObject({
      status: "loaded",
      reading: readingB,
    });

    first.resolve(response(readingA));
    await flushPromises();
    expect(harness.render(paperB).state).toMatchObject({
      status: "loaded",
      reading: readingB,
    });
    harness.unmount();
  });

  it("recovers from a 503 after retrying", async () => {
    const reading = makeFullReading();
    const paper = loadedPaper(reading.stable_id, "/reading.json");
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response(null, { ok: false, status: 503 }))
      .mockResolvedValueOnce(response(reading)) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);
    const harness = new HookHarness();

    harness.render(paper);
    await flushPromises();
    const failed = harness.render(paper);
    expect(failed.state).toMatchObject({
      status: "error",
      reading: null,
      error: "Full reading request failed (503)",
    });

    failed.retry();
    expect(harness.render(paper).state.status).toBe("loading");
    await flushPromises();
    expect(harness.render(paper).state).toMatchObject({
      status: "loaded",
      reading,
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    harness.unmount();
  });
});
