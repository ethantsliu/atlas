type ChangeSource = {
  addEventListener?: (type: string, listener: () => void) => void;
  atlasAutoEpoch?: number;
  autoRotate?: boolean;
  removeEventListener?: (type: string, listener: () => void) => void;
};

export function beginAutoChange(source: ChangeSource): void {
  source.atlasAutoEpoch = (source.atlasAutoEpoch ?? 0) + 1;
}

export function bindChange(
  source: ChangeSource | null | undefined,
  listener: () => void,
): () => void {
  let seenAutoEpoch = -1;
  const userChange = () => {
    if (source?.autoRotate) {
      const epoch = source.atlasAutoEpoch ?? 0;
      if (epoch === seenAutoEpoch) return;
      seenAutoEpoch = epoch;
    }
    listener();
  };
  source?.addEventListener?.("change", userChange);
  return () => source?.removeEventListener?.("change", userChange);
}
