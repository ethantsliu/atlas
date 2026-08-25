import { useEffect, useMemo, useState } from "react";
import { BookOpen, ChevronRight, Database, RefreshCw } from "lucide-react";
import { PaperDetailModal } from "../components/papers/Paper";
import { EmptyState, ResultStatus } from "../components/shared/Empty";
import { PageHead } from "../components/shared/Head";
import { useCorpus } from "../hooks/corpus";
import { filterPaperTitles } from "../lib/filters";
import { labelOf } from "../lib/text";
import type { Atlas, Paper } from "../types";

const PAGE_SIZE = 100;

type LibraryViewProps = {
  atlas: Atlas;
  query: string;
  onClearQuery: () => void;
};

export function LibraryView({ atlas, query, onClearQuery }: LibraryViewProps) {
  const [page, setPage] = useState(1);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const localRows = filterPaperTitles(atlas.papers, query);
  const corpus = useCorpus(query, page, PAGE_SIZE);
  const paperMap = useMemo(
    () => new Map(atlas.papers.map((paper) => [paper.id, paper])),
    [atlas.papers],
  );
  const hostedRows = corpus.matches.flatMap((match) => {
    const paper = paperMap.get(match.paperId);
    return paper ? [paper] : [];
  });
  const remote = corpus.active && hostedRows.length === corpus.matches.length;
  const rows = remote ? hostedRows : localRows;
  const total = remote ? corpus.total : localRows.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const visibleRows = remote ? rows : rows.slice(startIndex, startIndex + PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [query]);

  return (
    <main className="page">
      <PageHead
        icon={<BookOpen />}
        kicker="Evidence library"
        title={`${total.toLocaleString()} collection entries`}
        copy="Every summary carries a reading-depth label. Hosted full-text search spans titles, abstracts, routes, and compact readings; details remain in the reviewed static archive."
      />
      {query.trim().length >= 2 && (
        <aside className={`library-source ${remote ? "hosted" : "static"}`}>
          <Database size={16} aria-hidden="true" />
          <span>
            {remote
              ? "Hosted PostgreSQL full-text search · read only"
              : "Static title search fallback"}
            {corpus.error && ` · ${corpus.error}`}
          </span>
        </aside>
      )}
      <ResultStatus
        count={total}
        label="collection entry"
        plural="collection entries"
        query={query}
      />

      {corpus.loading && remote ? (
        <section className="library-loading" role="status" aria-live="polite">
          <RefreshCw className="spin" size={17} aria-hidden="true" /> Searching the
          hosted corpus…
        </section>
      ) : rows.length === 0 ? (
        <EmptyState
          title={
            query.trim() ? `No entries match “${query.trim()}”` : "No entries available"
          }
          copy="Try a broader concept, paper title, or author name."
          action={query.trim() ? "Clear search" : undefined}
          onReset={query.trim() ? onClearQuery : undefined}
        />
      ) : (
        <>
          <table className="table library-table">
            <caption className="sr-only">Collection entry library</caption>
            <thead>
              <tr className="table-head">
                <th scope="col">Entry</th>
                <th className="cluster-head" scope="col">
                  Clusters
                </th>
                <th scope="col">Evidence</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((paper) => (
                <tr className="table-row paper-row" key={paper.id}>
                  <th className="entry-cell" scope="row">
                    <b>{paper.title}</b>
                    <small>
                      {paper.authors?.slice(0, 3).join(", ") || paper.source}
                    </small>
                  </th>
                  <td className="cluster-cell">
                    <span className="chip-row">
                      {[...paper.topics, ...paper.tricks].slice(0, 3).map((route) => (
                        <i key={route.id}>{labelOf(route.id)}</i>
                      ))}
                    </span>
                  </td>
                  <td>
                    <span className={`depth ${paper.reading_depth}`}>
                      {paper.record_kind === "non_paper_context"
                        ? "Context"
                        : labelOf(paper.reading_depth)}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="paper-open"
                      onClick={() => setSelectedPaper(paper)}
                      aria-label={`Open ${paper.title} details`}
                    >
                      Open <ChevronRight size={14} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <nav className="pagination" aria-label="Collection entry library pages">
            <span>
              {startIndex + 1}–{Math.min(startIndex + PAGE_SIZE, total)} of{" "}
              {total.toLocaleString()}
            </span>
            <div>
              <button
                disabled={currentPage === 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                Previous
              </button>
              <b>
                Page {currentPage} of {pageCount}
              </b>
              <button
                disabled={currentPage === pageCount}
                onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
              >
                Next
              </button>
            </div>
          </nav>
        </>
      )}

      {selectedPaper && (
        <PaperDetailModal paper={selectedPaper} close={() => setSelectedPaper(null)} />
      )}
    </main>
  );
}
