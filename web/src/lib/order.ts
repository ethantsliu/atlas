export type PickRank = 1 | 2 | 3;

export type PickDepth = { depth: number; rank: PickRank };
export type PickJob = PickDepth & { run: () => void };

export type PickOrder = {
  begin: (stamp: number) => void;
  claim: (rank: PickRank, depth: number, run: () => void) => void;
  settle: () => void;
};

export function nearer(next: PickDepth, prior: PickDepth | null): boolean {
  if (!prior) return true;
  if (next.depth !== prior.depth) return next.depth < prior.depth;
  return next.rank >= prior.rank;
}

export function frontRank(items: PickDepth[]): PickRank | 0 {
  let best: PickDepth | null = null;
  for (const item of items) {
    if (Number.isFinite(item.depth) && nearer(item, best)) best = item;
  }
  return best?.rank ?? 0;
}

export function makeOrder(
  delay: (run: () => void) => void = (run) => void setTimeout(run, 250),
): PickOrder {
  let stamp = Number.NaN;
  let winner: PickJob | null = null;
  let job: PickJob | null = null;
  let queued = false;
  let ready = false;

  const flush = () => {
    if (!ready) return;
    const next = job;
    job = null;
    if (!next || !nearer(next, winner)) return;
    winner = next;
    next.run();
  };

  return {
    begin(next) {
      if (next === stamp) return;
      stamp = next;
      winner = null;
      job = null;
      queued = false;
      ready = false;
    },
    claim(rank, depth, run) {
      const next = { depth, rank, run };
      if (!Number.isFinite(depth) || !nearer(next, winner) || !nearer(next, job)) {
        return;
      }
      job = next;
      if (ready) {
        flush();
        return;
      }
      if (queued) return;
      queued = true;
      const queuedAt = stamp;
      delay(() => {
        if (stamp !== queuedAt) return;
        queued = false;
        ready = true;
        flush();
      });
    },
    settle() {
      queued = false;
      ready = true;
      flush();
    },
  };
}
