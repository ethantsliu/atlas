import { useEffect, useMemo, useState } from "react";
import {
  METHOD_CANDIDATE_NOTICE,
  METHOD_QUERY_DELAY_MS,
  METHOD_RELEASE_NOTICE,
  type MethodOverview,
  type MethodRow,
} from "../../lib/methods";
import { methodSummaryText, normalizeMethodQuery } from "../../lib/methodview";
import { MethodsClient, type MethodDetail } from "../../lib/methodroute";
import "./Methods.css";

const RESULT_LIMIT = 40;

type MethodsProps = {
  onCount?: (count: number) => void;
};

function Evidence({ detail }: { detail: MethodDetail }) {
  if (detail.availability === "release-only") {
    return (
      <div className="method-evidence">
        <p>{METHOD_RELEASE_NOTICE}</p>
        <a href={detail.download.url} target="_blank" rel="noreferrer">
          Download verified full candidate evidence
        </a>
      </div>
    );
  }
  const { candidate } = detail;
  return (
    <div className="method-evidence">
      <p>
        {candidate.kind === "method-noun" ? "Method noun" : "Process technique"} ·{" "}
        {candidate.firstYear}–{candidate.lastYear} ·{" "}
        {candidate.mentionCount.toLocaleString()} mentions
      </p>
      <ul>
        {candidate.evidence.map((item) => {
          const identifier = item.sourceId.replace(/^arxiv:/, "");
          return (
            <li key={`${item.sourceId}:${item.span[0]}:${item.span[1]}`}>
              <a
                href={`https://arxiv.org/abs/${identifier}`}
                target="_blank"
                rel="noreferrer"
              >
                {identifier}
              </a>{" "}
              <q>{item.text}</q>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function MethodList({
  rows,
  client,
}: {
  rows: readonly MethodRow[];
  client: MethodsClient;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<MethodDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) {
      setDetail(null);
      setFailed(false);
      return;
    }
    const controller = new AbortController();
    setDetail(null);
    setFailed(false);
    void client
      .detail(
        rows.find((row) => row.id === open)!,
        controller.signal,
      )
      .then(setDetail)
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [client, open, rows]);

  return (
    <ul className="catalog-list method-list" aria-label="Extracted method phrases">
      {rows.map((row) => {
        const expanded = open === row.id;
        return (
          <li key={row.id}>
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : row.id)}
            >
              <b>{row.label}</b>
              <span>Corpus-extracted candidate</span>
              <small>
                {row.supportCount.toLocaleString()} supporting papers ·{" "}
                {row.mentionCount.toLocaleString()} mentions
              </small>
            </button>
            {expanded && (
              <div className="method-detail" aria-live="polite">
                {detail ? (
                  <Evidence detail={detail} />
                ) : failed ? (
                  <p>Evidence is temporarily unavailable.</p>
                ) : (
                  <p>Loading source evidence…</p>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function Methods({ onCount }: MethodsProps) {
  const client = useMemo(() => new MethodsClient(), []);
  const [overview, setOverview] = useState<MethodOverview | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MethodRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [failed, setFailed] = useState(false);
  const normalized = normalizeMethodQuery(query);
  const searchable = normalized.split(" ").some((word) => word.length >= 3);

  useEffect(() => {
    const controller = new AbortController();
    void client
      .load(controller.signal)
      .then((value) => {
        setOverview(value);
        setLoading(false);
        onCount?.(value.summary.qualifiedCandidates);
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") {
          setFailed(true);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [client, onCount]);

  useEffect(() => {
    if (!overview || !searchable) {
      setResults(null);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timer = window.setTimeout(() => {
      void client
        .search(normalized, controller.signal)
        .then((rows) => {
          setResults(rows.slice(0, RESULT_LIMIT));
          setSearching(false);
        })
        .catch((error: unknown) => {
          if ((error as Error).name !== "AbortError") {
            setResults([]);
            setSearching(false);
          }
        });
    }, METHOD_QUERY_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [client, normalized, overview, searchable]);

  if (loading) return <p className="catalog-results">Loading method index…</p>;
  if (failed || !overview) {
    return (
      <div className="method-browser">
        <p className="catalog-results">Extracted method phrases are unavailable.</p>
        <p className="catalog-notice">{METHOD_CANDIDATE_NOTICE}</p>
      </div>
    );
  }

  const rows = results ?? overview.top;
  return (
    <div className="method-browser">
      <p className="method-summary">{methodSummaryText(overview.summary)}</p>
      <label className="catalog-search">
        Search extracted phrases
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search extracted phrases (3+ characters)"
        />
      </label>
      <label className="method-sort">
        Sort
        <select value="support" disabled>
          <option value="support">Most frequently supported</option>
        </select>
      </label>
      {normalized.length > 0 && !searchable && (
        <p className="catalog-results">Enter at least 3 characters to search.</p>
      )}
      {searching ? (
        <p className="catalog-results" aria-live="polite">
          Searching extracted phrases…
        </p>
      ) : rows.length ? (
        <MethodList rows={rows} client={client} />
      ) : (
        <p className="catalog-results" aria-live="polite">
          No matching extracted phrases.
        </p>
      )}
      <p className="catalog-results">
        Showing {rows.length.toLocaleString()} {results ? "matches" : "top phrases"}.
      </p>
      <p className="catalog-notice">{METHOD_CANDIDATE_NOTICE}</p>
    </div>
  );
}
