import { CalendarDays, CheckCircle2, ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Pager } from "../components/Pager";
import { EmptyState, ResultStatus } from "../components/shared/Empty";
import { useFeed } from "../hooks/feed";
import { useSearch } from "../hooks/search";
import { labelOf } from "../lib/text";
import type { DailyIndex, DailyPaper, HostedPaper } from "../types";

type DailyProps = {
  query: string;
  onClearQuery: () => void;
};

type Scope = "shortlist" | "all";
type Lane = "all" | DailyPaper["relevance"]["lane"];

const LANES: Lane[] = ["all", "core", "field", "math-stat", "adjacent"];
const PAGE_LIMIT = 30;

function matchesPaper(paper: DailyPaper, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  const text = [
    paper.title,
    paper.abstract,
    ...paper.authors,
    ...paper.categories,
    ...paper.topics.map((item) => item.id),
    ...paper.tricks.map((item) => item.id),
  ]
    .join(" ")
    .toLocaleLowerCase();
  return text.includes(needle);
}

function Score({ label, value }: { label: string; value: number }) {
  return (
    <span className="daily-score">
      <b>{value.toFixed(1)}</b>
      <small>{label}</small>
    </span>
  );
}

function TagList({ paper }: { paper: DailyPaper }) {
  const tags = [
    ...paper.topics.map((item) => ({ id: item.id, kind: "topic" })),
    ...paper.tricks.map((item) => ({ id: item.id, kind: "trick" })),
  ].slice(0, 6);
  if (!tags.length) return null;
  return (
    <div className="daily-tags" aria-label="Routed concepts">
      {tags.map((tag) => (
        <span className={tag.kind} key={`${tag.kind}-${tag.id}`}>
          {labelOf(tag.id)}
        </span>
      ))}
    </div>
  );
}

function DailyCard({
  paper,
  shortlisted,
  date,
}: {
  paper: DailyPaper;
  shortlisted: boolean;
  date?: string;
}) {
  return (
    <article className="daily-card">
      <div className="daily-card-head">
        <div>
          <div className="daily-kicker">
            <span className={`daily-lane ${paper.relevance.lane}`}>
              {labelOf(paper.relevance.lane)}
            </span>
            {shortlisted && <span className="daily-pick">interest shortlist</span>}
            {date && <span className="daily-result-date">{date}</span>}
          </div>
          <h2>{paper.title}</h2>
          <p className="daily-authors">{paper.authors.join(", ")}</p>
        </div>
        <div className="daily-scores" aria-label="Triage scores out of 10">
          <Score label="interest" value={paper.interest.score} />
          <Score label="relevance" value={paper.relevance.score} />
        </div>
      </div>
      <p className="daily-abstract">{paper.abstract}</p>
      <TagList paper={paper} />
      <div className="daily-reasons">
        {[...paper.relevance.reasons, ...paper.interest.reasons].map((reason) => (
          <span key={reason}>{reason}</span>
        ))}
      </div>
      <footer>
        <span>{paper.categories.join(" · ")}</span>
        <a href={paper.url} target="_blank" rel="noreferrer">
          arXiv:{paper.id} <ExternalLink size={14} aria-hidden="true" />
        </a>
      </footer>
    </article>
  );
}

function SearchNote({
  query,
  remote,
  days,
  error,
}: {
  query: string;
  remote: boolean;
  days: number;
  error: string | null;
}) {
  if (!query.trim()) return null;
  return (
    <aside className={`daily-search ${remote ? "remote" : "local"}`}>
      <CalendarDays size={17} aria-hidden="true" />
      <span>
        {remote
          ? `Searching ${days} hosted UTC days.`
          : "Searching the selected UTC day in the static archive."}
        {error && ` Hosted search failed: ${error}`}
      </span>
    </aside>
  );
}

function DailyHero({
  index,
  selected,
  source,
  fallback,
  select,
}: {
  index: DailyIndex | null;
  selected: string;
  source: "hosted" | "static";
  fallback: boolean;
  select: (date: string) => void;
}) {
  return (
    <header className="daily-hero">
      <div>
        <span className="eyebrow">Daily discovery</span>
        <h1>Every relevant ML submission, with a focused reading queue.</h1>
        <p>
          The intake scans every arXiv submission for the UTC day. Math, statistics, and
          adjacent fields enter only with explicit ML signals; interest ranking never
          removes a relevance-positive paper.
        </p>
      </div>
      <div className="daily-date">
        <span className={`daily-source ${source}`}>
          {source === "hosted" ? "Hosted search · read only" : "Static archive"}
        </span>
        <label htmlFor="daily-date">Intake date</label>
        <select
          id="daily-date"
          value={selected}
          onChange={(event) => select(event.target.value)}
          disabled={!index?.days.length}
        >
          {(index?.days ?? []).map((item) => (
            <option key={item.date} value={item.date}>
              {item.date} · {item.relevant_count} relevant
            </option>
          ))}
        </select>
        <span>UTC submission window</span>
        {fallback && <small>Hosted service unavailable; using the static copy.</small>}
      </div>
    </header>
  );
}

export function DailyView({ query, onClearQuery }: DailyProps) {
  const {
    index,
    day,
    selected,
    loading,
    error,
    source,
    fallback,
    hostedDays,
    select,
    retry,
  } = useFeed();
  const [scope, setScope] = useState<Scope>("shortlist");
  const [lane, setLane] = useState<Lane>("all");
  const [page, setPage] = useState(1);
  const shortlist = useMemo(() => new Set(day?.shortlist_ids ?? []), [day]);
  const localPapers = useMemo(
    () =>
      (day?.papers ?? []).filter(
        (paper) =>
          (scope === "all" || shortlist.has(paper.id)) &&
          (lane === "all" || paper.relevance.lane === lane) &&
          matchesPaper(paper, query),
      ),
    [day, lane, query, scope, shortlist],
  );
  const hosted = source === "hosted" && query.trim().length >= 2;
  const search = useSearch(query, lane, scope === "shortlist", page, hosted);
  const remote = hosted && !search.error;
  const papers: (DailyPaper | HostedPaper)[] = remote
    ? search.papers
    : localPapers.slice((page - 1) * PAGE_LIMIT, page * PAGE_LIMIT);
  const total = remote ? search.total : localPapers.length;

  useEffect(() => setPage(1), [lane, query, scope, selected]);

  return (
    <main className="daily-page">
      <DailyHero
        index={index}
        selected={selected}
        source={source}
        fallback={fallback}
        select={select}
      />

      {error && (
        <section className="daily-state" role="alert">
          <p>{error}</p>
          <button type="button" onClick={retry}>
            <RefreshCw size={15} aria-hidden="true" /> Retry
          </button>
        </section>
      )}
      {loading && !day && (
        <section className="daily-state" role="status" aria-live="polite">
          <RefreshCw className="spin" size={18} aria-hidden="true" /> Loading daily
          intake…
        </section>
      )}
      {!loading && !error && index?.days.length === 0 && (
        <EmptyState
          title="No daily intake yet"
          copy="Run the feed command to publish the first complete UTC day."
        />
      )}

      {day && (
        <>
          <section className="daily-metrics" aria-label="Daily intake coverage">
            <div>
              <b>{day.source.source_total.toLocaleString()}</b>
              <span>submissions scanned</span>
            </div>
            <div>
              <b>{day.relevant_count.toLocaleString()}</b>
              <span>retained as relevant</span>
            </div>
            <div>
              <b>{day.shortlist_count.toLocaleString()}</b>
              <span>interest shortlist</span>
            </div>
            <div className={day.source.complete ? "complete" : "incomplete"}>
              <CheckCircle2 size={19} aria-hidden="true" />
              <span>
                <b>{day.source.complete ? "Complete" : "Incomplete"}</b>
                {day.source.fetched_count.toLocaleString()} fetched ·{" "}
                {day.source.page_count} pages
              </span>
            </div>
          </section>

          <section className="daily-tools" aria-label="Daily feed filters">
            <div className="scope-tabs">
              {(["shortlist", "all"] as Scope[]).map((item) => (
                <button
                  type="button"
                  className={scope === item ? "active" : ""}
                  aria-pressed={scope === item}
                  onClick={() => setScope(item)}
                  key={item}
                >
                  {item === "all" ? "All relevant" : "Interest shortlist"}
                </button>
              ))}
            </div>
            <div className="lane-tabs">
              {LANES.map((item) => (
                <button
                  type="button"
                  className={lane === item ? "active" : ""}
                  aria-pressed={lane === item}
                  onClick={() => setLane(item)}
                  key={item}
                >
                  {labelOf(item)}
                </button>
              ))}
            </div>
          </section>

          <SearchNote
            query={query}
            remote={remote}
            days={hostedDays}
            error={search.error}
          />

          <ResultStatus count={total} label="daily paper" query={query} />
          {remote && search.loading ? (
            <section className="daily-state" role="status" aria-live="polite">
              <RefreshCw className="spin" size={18} aria-hidden="true" /> Searching the
              hosted paper index…
            </section>
          ) : papers.length ? (
            <section className="daily-list" aria-label="Daily papers">
              {papers.map((paper) => (
                <DailyCard
                  key={`${"date" in paper ? paper.date : selected}-${paper.id}`}
                  paper={paper}
                  shortlisted={
                    "shortlisted" in paper ? paper.shortlisted : shortlist.has(paper.id)
                  }
                  date={"date" in paper ? paper.date : undefined}
                />
              ))}
            </section>
          ) : (
            <EmptyState
              title="No papers match these filters"
              copy="Try another category lane, show all relevant papers, or clear the search."
              action={query ? "Clear search" : undefined}
              onReset={query ? onClearQuery : undefined}
            />
          )}
          <Pager page={page} total={total} limit={PAGE_LIMIT} onPage={setPage} />
        </>
      )}
    </main>
  );
}
