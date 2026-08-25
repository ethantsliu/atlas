import type { WebglStatus } from "../../hooks/webgl";
import "./status.css";

type StatusProps = {
  status: WebglStatus;
  onRetry: () => void;
};

export function WebglStatus({ status, onRetry }: StatusProps) {
  if (status === "ready" || status === "unsupported") return null;
  const message =
    status === "lost"
      ? "3D view paused. You’re in the 2D compatibility view."
      : "Checking whether 3D rendering is available…";
  return (
    <aside className="graph-status" role="status" aria-live="polite" aria-atomic="true">
      <span>{message}</span>
      <button type="button" onClick={onRetry} disabled={status === "retrying"}>
        {status === "retrying" ? "Checking…" : "Retry 3D"}
      </button>
    </aside>
  );
}
