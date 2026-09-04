import { useEffect, useMemo, useState } from "react";
import { SearchCheck, Users } from "lucide-react";
import { fetchCatalog, type Catalog } from "../../lib/catalog";
import {
  DIRECTION_EVIDENCE,
  filterDirectionIdeas,
  projectDirectionIdeas,
  type DirectionIdea,
} from "../../lib/directions";
import { ResultStatus } from "../shared/Empty";
import "./Directions.css";

const INITIAL_ROWS = 18;
const PAGE_ROWS = 30;

function SupportLinks({ idea }: { idea: DirectionIdea }) {
  return (
    <ul aria-label="Deterministic corpus reference sample">
      {idea.supportIds.map((id) => {
        const arxivId = id.replace(/^arxiv:/, "");
        return (
          <li key={id}>
            <a
              href={`https://arxiv.org/abs/${arxivId}`}
              target="_blank"
              rel="noreferrer"
            >
              {arxivId}
            </a>
          </li>
        );
      })}
    </ul>
  );
}

function DirectionCard({ idea }: { idea: DirectionIdea }) {
  return (
    <li>
      <details>
        <summary>
          <b>{idea.question}</b>
          <span>Paper-grounded research idea · open for community review</span>
          <small>
            {idea.supportCount.toLocaleString()} route matches across {idea.yearCount}{" "}
            years
          </small>
        </summary>
        <p>{DIRECTION_EVIDENCE}</p>
        <dl>
          <div>
            <dt>arXiv subject</dt>
            <dd>{idea.subjectId}</dd>
          </div>
          <div>
            <dt>Technique family</dt>
            <dd>{idea.techniqueLabel}</dd>
          </div>
        </dl>
        <small>Deterministic corpus reference sample</small>
        <SupportLinks idea={idea} />
      </details>
    </li>
  );
}

export function DirectionIdeasList({
  catalog,
  query,
}: {
  catalog: Catalog;
  query: string;
}) {
  const [limit, setLimit] = useState(INITIAL_ROWS);
  const ideas = useMemo(() => projectDirectionIdeas(catalog), [catalog]);
  const matching = useMemo(() => filterDirectionIdeas(ideas, query), [ideas, query]);
  useEffect(() => setLimit(INITIAL_ROWS), [query, catalog.summary.catalogDigest]);
  const visible = matching.slice(0, limit);
  const remaining = matching.length - visible.length;

  return (
    <section className="direction-ideas" aria-labelledby="direction-ideas-title">
      <header className="brief-section-head">
        <span>
          <Users size={13} /> {ideas.length.toLocaleString()} paper-grounded research{" "}
          {ideas.length === 1 ? "idea" : "ideas"}
        </span>
        <h2 id="direction-ideas-title">Research ideas for community review</h2>
        <p>
          One idea is projected from every qualifying arXiv subject × technique
          direction in the {catalog.summary.sourceCount.toLocaleString()}-paper catalog.
          This collection is separate from Atlas&apos;s researched drafts and structured
          provisional ideas.
        </p>
      </header>
      <ResultStatus
        count={matching.length}
        label="paper-grounded research idea"
        query={query}
      />
      {matching.length === 0 ? (
        <p className="direction-empty">No paper-grounded research ideas match.</p>
      ) : (
        <ul className="direction-list" aria-label="Paper-grounded research ideas">
          {visible.map((idea) => (
            <DirectionCard idea={idea} key={idea.id} />
          ))}
        </ul>
      )}
      {remaining > 0 && (
        <div className="direction-actions">
          <button
            type="button"
            className="direction-more"
            onClick={() => setLimit((value) => value + PAGE_ROWS)}
          >
            Show {Math.min(PAGE_ROWS, remaining).toLocaleString()} more ·{" "}
            {remaining.toLocaleString()} remaining
          </button>
        </div>
      )}
      <p className="direction-notice">
        <SearchCheck size={13} /> Search evaluates all {ideas.length.toLocaleString()}{" "}
        ideas before pagination. Community review is required before an idea can enter
        the structured or researched collections.
      </p>
    </section>
  );
}

export function DirectionReviewQueue({
  query,
  onCount,
}: {
  query: string;
  onCount?: (count: number | null) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchCatalog(controller.signal)
      .then((value) => {
        setCatalog(value);
        setError(null);
        onCount?.(value.summary.candidateDirections);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Catalog request failed");
        onCount?.(null);
      });
    return () => controller.abort();
  }, [onCount]);

  if (error) {
    return (
      <section className="direction-ideas unavailable" role="status">
        <b>Paper-grounded community review ideas unavailable</b>
        <p>{error}</p>
      </section>
    );
  }
  if (!catalog) {
    return (
      <section className="direction-ideas unavailable" role="status" aria-busy="true">
        Loading paper-grounded community review ideas…
      </section>
    );
  }
  return <DirectionIdeasList catalog={catalog} query={query} />;
}
