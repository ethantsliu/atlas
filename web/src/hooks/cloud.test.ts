import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CloudData, CloudManifest, CloudStep } from "../lib/cloud";

type Cleanup = void | (() => void);
type EffectSlot = { cleanup: Cleanup; deps: readonly unknown[] };
type PendingEffect = {
  index: number;
  setup: () => Cleanup;
  deps: readonly unknown[];
};

const cloudMocks = vi.hoisted(() => ({
  createCloud: vi.fn(),
  fetchCloud: vi.fn(),
  streamCloud: vi.fn(),
}));

let activeHarness: HookHarness | null = null;

vi.mock("react", () => ({
  useCallback: <Value>(callback: Value) => callback,
  useEffect: (setup: () => Cleanup, deps: readonly unknown[]) => {
    if (!activeHarness) throw new Error("Hook effect rendered outside its harness");
    activeHarness.useEffect(setup, deps);
  },
  useRef: <Value>(initial: Value) => {
    if (!activeHarness) throw new Error("Hook ref rendered outside its harness");
    return activeHarness.useRef(initial);
  },
  useState: <Value>(initial: Value | (() => Value)) => {
    if (!activeHarness) throw new Error("Hook state rendered outside its harness");
    return activeHarness.useState(initial);
  },
}));

vi.mock("../lib/cloud", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/cloud")>();
  return { ...original, ...cloudMocks };
});

import { useCloud } from "./cloud";

class HookHarness {
  private states: unknown[] = [];
  private refs: { current: unknown }[] = [];
  private effects: EffectSlot[] = [];
  private pending: PendingEffect[] = [];
  private stateIndex = 0;
  private refIndex = 0;
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

  useRef<Value>(initial: Value): { current: Value } {
    const index = this.refIndex++;
    if (!(index in this.refs)) this.refs[index] = { current: initial };
    return this.refs[index] as { current: Value };
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

  render(enabled: boolean): ReturnType<typeof useCloud> {
    let result: ReturnType<typeof useCloud>;
    do {
      this.dirty = false;
      this.stateIndex = 0;
      this.refIndex = 0;
      this.effectIndex = 0;
      this.pending = [];
      activeHarness = this;
      try {
        result = useCloud(enabled);
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
    this.refs = [];
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
  reject: (reason: unknown) => void;
};

function deferred<Value>(): Deferred<Value> {
  let resolve!: (value: Value) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Value>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

function cloudData(total = 4): CloudData {
  return {
    positions: new Float32Array(total * 3),
    scopes: new Uint8Array(total),
    ranges: [],
    loaded: 0,
    radius: 0,
  };
}

const EMPTY_STATE = {
  manifest: null,
  data: null,
  loading: false,
  error: null,
};

async function flushPromises(): Promise<void> {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

beforeEach(() => {
  activeHarness = null;
  vi.clearAllMocks();
});

describe("progressive paper cloud state", () => {
  it("does no cloud work while disabled", async () => {
    const harness = new HookHarness();

    expect(harness.render(false)).toMatchObject(EMPTY_STATE);
    await flushPromises();
    expect(harness.render(false)).toMatchObject(EMPTY_STATE);
    expect(cloudMocks.fetchCloud).not.toHaveBeenCalled();
    expect(cloudMocks.createCloud).not.toHaveBeenCalled();
    expect(cloudMocks.streamCloud).not.toHaveBeenCalled();
    harness.unmount();
  });

  it("reuses one completed cloud across repeated re-entry", async () => {
    const manifest = { count: 4 } as CloudManifest;
    const data = cloudData();
    data.loaded = manifest.count;
    cloudMocks.fetchCloud.mockResolvedValue(manifest);
    cloudMocks.createCloud.mockReturnValue(data);
    cloudMocks.streamCloud.mockResolvedValue(data);
    const harness = new HookHarness();

    harness.render(true);
    await flushPromises();
    const complete = harness.render(true);
    expect(complete).toMatchObject({ manifest, data, loading: false, error: null });
    const positions = data.positions.buffer;
    const scopes = data.scopes.buffer;

    for (let entry = 0; entry < 3; entry += 1) {
      expect(harness.render(false)).toMatchObject(EMPTY_STATE);
      const restored = harness.render(true);
      expect(restored).toMatchObject({ manifest, data, loading: false, error: null });
      expect(restored.data?.positions.buffer).toBe(positions);
      expect(restored.data?.scopes.buffer).toBe(scopes);
    }
    expect(cloudMocks.fetchCloud).toHaveBeenCalledTimes(1);
    expect(cloudMocks.createCloud).toHaveBeenCalledTimes(1);
    expect(cloudMocks.streamCloud).toHaveBeenCalledTimes(1);
    harness.unmount();
  });

  it("discards an aborted partial load and ignores its late completion", async () => {
    const manifest = { count: 4 } as CloudManifest;
    const firstData = cloudData();
    const secondData = cloudData();
    const first = deferred<CloudData>();
    const second = deferred<CloudData>();
    let firstSignal: AbortSignal | undefined;
    let firstProgress: ((step: CloudStep) => void) | undefined;
    let secondProgress: ((step: CloudStep) => void) | undefined;
    cloudMocks.fetchCloud.mockResolvedValue(manifest);
    cloudMocks.createCloud
      .mockReturnValueOnce(firstData)
      .mockReturnValueOnce(secondData);
    cloudMocks.streamCloud
      .mockImplementationOnce(
        async (
          _manifest: CloudManifest,
          _data: CloudData,
          signal: AbortSignal,
          onStep?: (step: CloudStep) => void,
        ) => {
          firstSignal = signal;
          firstProgress = onStep;
          return first.promise;
        },
      )
      .mockImplementationOnce(
        async (
          _manifest: CloudManifest,
          _data: CloudData,
          _signal: AbortSignal,
          onStep?: (step: CloudStep) => void,
        ) => {
          secondProgress = onStep;
          return second.promise;
        },
      );
    const harness = new HookHarness();

    harness.render(true);
    await flushPromises();
    firstData.loaded = 2;
    firstProgress?.({ start: 0, count: 2, loaded: 2, total: 4 });
    expect(harness.render(true).data).toBe(firstData);

    expect(harness.render(false)).toMatchObject(EMPTY_STATE);
    expect(firstSignal?.aborted).toBe(true);
    harness.render(true);
    await flushPromises();
    expect(harness.render(true).data).toBe(secondData);

    firstData.loaded = 4;
    firstProgress?.({ start: 2, count: 2, loaded: 4, total: 4 });
    first.resolve(firstData);
    await flushPromises();
    expect(harness.render(true).data).toBe(secondData);

    secondData.loaded = 4;
    secondProgress?.({ start: 0, count: 4, loaded: 4, total: 4 });
    second.resolve(secondData);
    await flushPromises();
    expect(harness.render(true)).toMatchObject({
      manifest,
      data: secondData,
      loading: false,
      error: null,
    });
    harness.render(false);
    expect(harness.render(true).data).toBe(secondData);
    expect(cloudMocks.fetchCloud).toHaveBeenCalledTimes(2);
    expect(cloudMocks.createCloud).toHaveBeenCalledTimes(2);
    expect(cloudMocks.streamCloud).toHaveBeenCalledTimes(2);
    harness.unmount();
  });

  it("finishes an empty but valid cloud without waiting for a progress step", async () => {
    const manifest = { count: 0 } as CloudManifest;
    const data = cloudData(0);
    cloudMocks.fetchCloud.mockResolvedValue(manifest);
    cloudMocks.createCloud.mockReturnValue(data);
    cloudMocks.streamCloud.mockResolvedValue(data);
    const harness = new HookHarness();

    harness.render(true);
    await flushPromises();

    expect(harness.render(true)).toMatchObject({
      manifest,
      data,
      loading: false,
      error: null,
    });
    harness.unmount();
  });

  it("publishes once and keeps the same data identity through progressive steps", async () => {
    const manifest = { count: 4 } as CloudManifest;
    const data = cloudData();
    const completion = deferred<CloudData>();
    let progress: ((step: CloudStep) => void) | undefined;
    cloudMocks.fetchCloud.mockResolvedValue(manifest);
    cloudMocks.createCloud.mockReturnValue(data);
    cloudMocks.streamCloud.mockImplementation(
      async (
        _manifest: CloudManifest,
        _data: CloudData,
        _signal: AbortSignal,
        onStep?: (step: CloudStep) => void,
      ) => {
        progress = onStep;
        return completion.promise;
      },
    );
    const harness = new HookHarness();

    expect(harness.render(true)).toMatchObject({
      manifest: null,
      data: null,
      loading: true,
      error: null,
    });
    await flushPromises();

    const opened = harness.render(true);
    expect(opened.manifest).toBe(manifest);
    expect(opened.data).toBe(data);
    expect(opened.data?.loaded).toBe(0);
    expect(opened.loading).toBe(true);

    const positions = data.positions.buffer;
    const scopes = data.scopes.buffer;
    data.loaded = 2;
    progress?.({ start: 0, count: 2, loaded: 2, total: 4 });
    const partial = harness.render(true);
    expect(partial.data).toBe(opened.data);
    expect(partial.data?.positions.buffer).toBe(positions);
    expect(partial.data?.scopes.buffer).toBe(scopes);
    expect(partial.data?.loaded).toBe(2);
    expect(partial.loading).toBe(true);

    data.loaded = 4;
    progress?.({ start: 2, count: 2, loaded: 4, total: 4 });
    completion.resolve(data);
    await flushPromises();
    const complete = harness.render(true);
    expect(complete.data).toBe(opened.data);
    expect(complete.data?.loaded).toBe(4);
    expect(complete.loading).toBe(false);
    expect(complete.error).toBeNull();
    harness.unmount();
  });

  it("preserves partial data after failure and allocates fresh storage on retry", async () => {
    const manifest = { count: 4 } as CloudManifest;
    const partialData = cloudData();
    const recoveredData = cloudData();
    const first = deferred<CloudData>();
    const second = deferred<CloudData>();
    let firstProgress: ((step: CloudStep) => void) | undefined;
    let secondProgress: ((step: CloudStep) => void) | undefined;
    cloudMocks.fetchCloud.mockResolvedValue(manifest);
    cloudMocks.createCloud
      .mockReturnValueOnce(partialData)
      .mockReturnValueOnce(recoveredData);
    cloudMocks.streamCloud
      .mockImplementationOnce(
        async (
          _manifest: CloudManifest,
          _data: CloudData,
          _signal: AbortSignal,
          onStep?: (step: CloudStep) => void,
        ) => {
          firstProgress = onStep;
          return first.promise;
        },
      )
      .mockImplementationOnce(
        async (
          _manifest: CloudManifest,
          _data: CloudData,
          _signal: AbortSignal,
          onStep?: (step: CloudStep) => void,
        ) => {
          secondProgress = onStep;
          return second.promise;
        },
      );
    const harness = new HookHarness();

    harness.render(true);
    await flushPromises();
    expect(harness.render(true).data).toBe(partialData);
    partialData.loaded = 2;
    firstProgress?.({ start: 0, count: 2, loaded: 2, total: 4 });
    first.reject(new Error("shard unavailable"));
    await flushPromises();

    const failed = harness.render(true);
    expect(failed).toMatchObject({
      manifest,
      data: partialData,
      loading: false,
      error: "shard unavailable",
    });
    expect(failed.data?.loaded).toBe(2);

    failed.retry();
    expect(harness.render(true)).toMatchObject({
      manifest: null,
      data: null,
      loading: true,
      error: null,
    });
    await flushPromises();
    const retrying = harness.render(true);
    expect(retrying.data).toBe(recoveredData);
    expect(retrying.data).not.toBe(partialData);
    expect(retrying.data?.positions.buffer).not.toBe(partialData.positions.buffer);

    recoveredData.loaded = 4;
    secondProgress?.({ start: 0, count: 4, loaded: 4, total: 4 });
    second.resolve(recoveredData);
    await flushPromises();
    expect(harness.render(true)).toMatchObject({
      manifest,
      data: recoveredData,
      loading: false,
      error: null,
    });
    expect(cloudMocks.fetchCloud).toHaveBeenCalledTimes(2);
    expect(cloudMocks.createCloud).toHaveBeenCalledTimes(2);
    harness.unmount();
  });
});
