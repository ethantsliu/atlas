import type { WebglStatus } from "../../hooks/webgl";
import type { RenderMode } from "../../hooks/webgl";
import "./status.css";

type StatusProps = {
  status: WebglStatus;
  requested: RenderMode;
  onRetry: () => void;
};

export function WebglStatus({ status, requested, onRetry }: StatusProps) {
  if (status === "ready" || requested === "2d") return null;
  const message =
    status === "lost"
      ? "3D stopped; using the 2D fallback."
      : status === "unsupported"
        ? "3D unavailable; using the 2D fallback."
        : "Checking 3D…";
  return (
    <aside className="graph-status" role="status" aria-live="polite" aria-atomic="true">
      <span>{message}</span>
      <button type="button" onClick={onRetry} disabled={status === "retrying"}>
        {status === "retrying" ? "Checking…" : "Retry 3D"}
      </button>
    </aside>
  );
}
