import type { Paper } from "../../types";
import { PaperDetailModal } from "../papers/Paper";

type LoadProps = {
  loading: boolean;
  error: string | null;
  retry: () => void;
};

export function PaperState({ loading, error, retry }: LoadProps) {
  if (!loading && !error) return null;
  return (
    <aside
      className="paper-state"
      role={error ? "alert" : "status"}
      aria-live="polite"
      aria-atomic="true"
      aria-busy={loading}
    >
      <span>{error ? `Paper index unavailable: ${error}` : "Loading papers…"}</span>
      {error && (
        <button type="button" onClick={retry}>
          Retry papers
        </button>
      )}
    </aside>
  );
}

type SheetProps = {
  paper: Paper | null;
  close: () => void;
};

export function PaperSheet({ paper, close }: SheetProps) {
  return paper ? <PaperDetailModal paper={paper} close={close} /> : null;
}
