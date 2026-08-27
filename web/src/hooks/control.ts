type ChangeSource = {
  addEventListener?: (type: string, listener: () => void) => void;
  removeEventListener?: (type: string, listener: () => void) => void;
};

export function bindChange(
  source: ChangeSource | null | undefined,
  listener: () => void,
): () => void {
  source?.addEventListener?.("change", listener);
  return () => source?.removeEventListener?.("change", listener);
}
