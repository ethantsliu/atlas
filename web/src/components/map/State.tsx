import type { Paper } from "../../types";
import { PaperDetailModal } from "../papers/Paper";

type LoadProps = {
  loading: boolean;
  error: string | null;
  retry: () => void;
};

type NoticeProps = LoadProps & {
  loadingText: string;
  errorPrefix: string;
  retryText: string;
};

function LoadNotice({
  loading,
  error,
  retry,
  loadingText,
  errorPrefix,
  retryText,
}: NoticeProps) {
  if (!loading && !error) return null;
  return (
    <aside
      className="paper-state"
      role={error ? "alert" : "status"}
      aria-live="polite"
      aria-atomic="true"
      aria-busy={loading}
    >
      <span>{error ? `${errorPrefix}: ${error}` : loadingText}</span>
      {error && (
        <button
          type="button"
          onClick={(event) => {
            if (event.detail === 0) {
              document.querySelector<HTMLElement>(".graph-wrap")?.focus();
            }
            retry();
          }}
        >
          {retryText}
        </button>
      )}
    </aside>
  );
}

export function PaperState(props: LoadProps) {
  return (
    <LoadNotice
      {...props}
      loadingText="Loading papers…"
      errorPrefix="Paper index unavailable"
      retryText="Retry papers"
    />
  );
}

export function CloudState(props: LoadProps) {
  return (
    <LoadNotice
      {...props}
      loadingText="Loading historical papers…"
      errorPrefix="Historical papers unavailable"
      retryText="Retry historical papers"
    />
  );
}

type SheetProps = {
  paper: Paper | null;
  close: () => void;
};

export function PaperSheet({ paper, close }: SheetProps) {
  return paper ? <PaperDetailModal paper={paper} close={close} /> : null;
}
