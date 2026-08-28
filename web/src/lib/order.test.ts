import { describe, expect, it, vi } from "vitest";
import { frontRank, makeOrder, nearer, type PickJob } from "./order";

function job(depth: number, rank: 1 | 2 | 3): PickJob {
  return { depth, rank, run: vi.fn() };
}

describe("hover order", () => {
  it("uses camera depth before semantic rank", () => {
    expect(nearer(job(4, 1), job(8, 3))).toBe(true);
    expect(nearer(job(8, 3), job(4, 1))).toBe(false);
  });

  it("uses semantic rank only to settle a depth tie", () => {
    expect(nearer(job(4, 3), job(4, 1))).toBe(true);
    expect(nearer(job(4, 1), job(4, 3))).toBe(false);
  });

  it("selects the nearest hover layer", () => {
    expect(
      frontRank([
        { depth: 7, rank: 3 },
        { depth: 3, rank: 1 },
        { depth: 5, rank: 2 },
      ]),
    ).toBe(1);
  });
});

describe("pick order", () => {
  it("keeps the nearest claim in one gesture", () => {
    const tasks: Array<() => void> = [];
    const order = makeOrder((run) => tasks.push(run));
    const archive = vi.fn();
    const curated = vi.fn();
    const core = vi.fn();

    order.begin(1);
    order.claim(1, 4, archive);
    order.claim(2, 6, curated);
    order.claim(3, 8, core);
    expect(tasks).toHaveLength(1);
    expect(archive).not.toHaveBeenCalled();
    order.settle();

    expect(archive).toHaveBeenCalledOnce();
    expect(curated).not.toHaveBeenCalled();
    expect(core).not.toHaveBeenCalled();
  });

  it("rejects a late lower claim until the next gesture", () => {
    const tasks: Array<() => void> = [];
    const order = makeOrder((run) => tasks.push(run));
    const core = vi.fn();
    const archive = vi.fn();

    order.begin(1);
    order.claim(3, 3, core);
    order.settle();
    order.claim(1, 5, archive);
    expect(archive).not.toHaveBeenCalled();

    order.begin(2);
    order.claim(1, 7, archive);
    order.settle();
    expect(archive).toHaveBeenCalledOnce();
  });

  it("releases a late metadata claim after background settlement", () => {
    const order = makeOrder();
    const archive = vi.fn();

    order.begin(1);
    order.settle();
    order.claim(1, 2, archive);

    expect(archive).toHaveBeenCalledOnce();
  });

  it("uses the fallback only when ForceGraph does not settle", () => {
    const tasks: Array<() => void> = [];
    const order = makeOrder((run) => tasks.push(run));
    const curated = vi.fn();

    order.begin(1);
    order.claim(2, 2, curated);
    expect(curated).not.toHaveBeenCalled();
    tasks.shift()?.();

    expect(curated).toHaveBeenCalledOnce();
  });
});
