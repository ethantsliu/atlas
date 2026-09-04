import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  fetchCatalog,
  type Catalog,
  type CatalogDirection,
  type CatalogSummary,
} from "../../lib/catalog";
import { labelOf } from "../../lib/text";
import "./Catalog.css";

const PAGE_SIZE = 40;
// The count in the currently published, immutable full-corpus method release.
// The interactive method browser validates its own index before showing any rows.
export const PUBLISHED_METHOD_CANDIDATES = 129_806;
const Methods = lazy(() => import("./Methods"));

type CatalogTab = "subjects" | "directions" | "questions" | "methods";

const QUESTION_NOTICE =
  "These are automatically projected research-question candidates, not reviewed ideas, recommendations, novelty findings, or feasibility assessments. The curated Atlas brief collection remains separate, with review status shown per brief.";
const QUESTION_EVIDENCE =
  "The references establish only corpus co-occurrence between this arXiv subject and curated technique family; they do not establish novelty, causality, feasibility, or effectiveness.";

export function catalogDescription(summary: CatalogSummary, ideas: number): string {
  return `${summary.broadAreas.toLocaleString()} curated broad-topic lenses and ${summary.techniqueFamilies.toLocaleString()} curated technique-family lenses organize the map; they are not corpus totals. Corpus-derived layers cover ${summary.sourceCount.toLocaleString()} papers, ${summary.arxivSubjects.toLocaleString()} arXiv subjects, and ${summary.candidateDirections.toLocaleString()} of ${summary.eligibleDirections.toLocaleString()} qualifying unreviewed research-question candidates. The ${ideas.toLocaleString()} curated briefs remain separate, with review status shown per brief.`;
}

function includes(value: string, query: string): boolean {
  return value.toLocaleLowerCase().includes(query.toLocaleLowerCase());
}

function directionName(
  direction: CatalogDirection,
  techniques: ReadonlyMap<string, string>,
): string {
  return `${direction.subjectId} × ${techniques.get(direction.techniqueId) ?? labelOf(direction.techniqueId)}`;
}

export function candidateQuestion(subject: string, technique: string): string {
  return `Across research classified under ${subject}, under which documented conditions is ${technique} associated with better, worse, or unchanged reported outcomes?`;
}

function CandidateQuestions({
  directions,
  techniques,
}: {
  directions: readonly CatalogDirection[];
  techniques: ReadonlyMap<string, string>;
}) {
  return (
    <div className="question-browser">
      <ul className="catalog-list directions" aria-label="Candidate questions">
        {directions.map((direction) => (
          <li key={direction.id}>
            <details>
              <summary>
                <b>
                  {candidateQuestion(
                    direction.subjectId,
                    techniques.get(direction.techniqueId) ??
                      labelOf(direction.techniqueId),
                  )}
                </b>
                <span>Unreviewed candidate question</span>
                <small>
                  {direction.supportCount.toLocaleString()} supporting papers · novelty
                  and feasibility not assessed
                </small>
              </summary>
              <p>{QUESTION_EVIDENCE}</p>
              <ul>
                {direction.supportIds.map((id) => {
                  const identifier = id.replace(/^arxiv:/, "");
                  return (
                    <li key={id}>
                      <a
                        href={`https://arxiv.org/abs/${identifier}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {identifier}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </details>
          </li>
        ))}
      </ul>
      <p className="catalog-notice">{QUESTION_NOTICE}</p>
    </div>
  );
}

export function CorpusExplorer({ catalog }: { catalog: Catalog }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<CatalogTab>("questions");
  const [query, setQuery] = useState("");
  const [methodCount, setMethodCount] = useState<number | null>(
    PUBLISHED_METHOD_CANDIDATES,
  );
  const techniques = useMemo(
    () => new Map(catalog.techniques.map((row) => [row.id, row.label])),
    [catalog.techniques],
  );
  const term = query.trim().toLocaleLowerCase();
  const subjects = useMemo(
    () =>
      catalog.subjects
        .filter((row) => !term || includes(row.id, term) || includes(row.label, term))
        .slice(0, PAGE_SIZE),
    [catalog.subjects, term],
  );
  const directions = useMemo(
    () =>
      catalog.directions
        .filter((row) => {
          if (!term) return true;
          const technique = techniques.get(row.techniqueId) ?? row.techniqueId;
          return (
            includes(row.subjectId, term) ||
            includes(row.techniqueId, term) ||
            includes(technique, term)
          );
        })
        .slice(0, PAGE_SIZE),
    [catalog.directions, techniques, term],
  );

  return (
    <div className="catalog-browser">
      <button
        className="catalog-open"
        type="button"
        aria-expanded={open}
        aria-controls="corpus-catalog"
        onClick={() => setOpen((value) => !value)}
      >
        {open
          ? "Close corpus explorer"
          : `Explore ${catalog.summary.candidateDirections.toLocaleString()} candidate questions`}
      </button>
      {open && (
        <section id="corpus-catalog" aria-label="Full-corpus taxonomy">
          <div className="catalog-tabs" role="group" aria-label="Catalog layer">
            <button
              type="button"
              aria-pressed={tab === "questions"}
              onClick={() => setTab("questions")}
            >
              Candidate questions (
              {catalog.summary.candidateDirections.toLocaleString()})
            </button>
            <button
              type="button"
              aria-pressed={tab === "subjects"}
              onClick={() => setTab("subjects")}
            >
              Subjects ({catalog.summary.arxivSubjects.toLocaleString()})
            </button>
            <button
              type="button"
              aria-pressed={tab === "directions"}
              onClick={() => setTab("directions")}
            >
              Directions ({catalog.summary.candidateDirections.toLocaleString()})
            </button>
            <button
              type="button"
              aria-pressed={tab === "methods"}
              onClick={() => setTab("methods")}
            >
              Extracted method phrases
              {methodCount === null ? "" : ` (${methodCount.toLocaleString()})`}
            </button>
          </div>
          {tab !== "methods" && (
            <label className="catalog-search">
              Search {tab}
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={tab === "subjects" ? "cs.LG" : "subject or technique"}
              />
            </label>
          )}
          {tab === "subjects" ? (
            <ul className="catalog-list">
              {subjects.map((subject) => (
                <li key={subject.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuery(subject.id);
                      setTab("directions");
                    }}
                  >
                    <b>{subject.label}</b>
                    <span>{subject.paperCount.toLocaleString()} papers</span>
                    <small>{subject.primaryPaperCount.toLocaleString()} primary</small>
                  </button>
                </li>
              ))}
            </ul>
          ) : tab === "directions" ? (
            <ul className="catalog-list directions">
              {directions.map((direction) => (
                <li key={direction.id}>
                  <details>
                    <summary>
                      <b>{directionName(direction, techniques)}</b>
                      <span>Candidate direction</span>
                      <small>
                        {direction.supportCount.toLocaleString()} papers ·{" "}
                        {direction.yearCount} years · NPMI {direction.npmi.toFixed(3)}
                      </small>
                    </summary>
                    <p>
                      Corpus association, not a reviewed claim of novelty, causality, or
                      feasibility. Deterministic support sample:
                    </p>
                    <ul>
                      {direction.supportIds.map((id) => {
                        const identifier = id.replace(/^arxiv:/, "");
                        return (
                          <li key={id}>
                            <a
                              href={`https://arxiv.org/abs/${identifier}`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {identifier}
                            </a>
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                </li>
              ))}
            </ul>
          ) : tab === "questions" ? (
            <CandidateQuestions directions={directions} techniques={techniques} />
          ) : (
            <Suspense fallback={<p className="catalog-results">Loading methods…</p>}>
              <Methods onCount={setMethodCount} />
            </Suspense>
          )}
          {tab !== "methods" && (
            <>
              <p className="catalog-results">
                Showing {tab === "subjects" ? subjects.length : directions.length}{" "}
                matching {tab}. Refine the search to narrow the catalog.
              </p>
              {tab !== "questions" && (
                <p className="catalog-notice">{catalog.summary.notice}</p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default function CatalogCopy({
  enabled,
  ideas,
}: {
  enabled: boolean;
  ideas: number;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void fetchCatalog(controller.signal)
      .then((value) => {
        setCatalog(value);
        setFailed(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setCatalog(null);
          setFailed(true);
        }
      });
    return () => controller.abort();
  }, [enabled]);

  return (
    <div className="catalog-copy">
      <p className="range-copy">
        {catalog
          ? catalogDescription(catalog.summary, ideas)
          : failed
            ? "The full-corpus taxonomy is temporarily unavailable. Curated map lenses and briefs remain available."
            : "Loading full-corpus taxonomy…"}
      </p>
      {catalog && (
        <>
          <dl className="catalog-stats" aria-label="Full-corpus layers">
            <div>
              <dt>{catalog.summary.sourceCount.toLocaleString()}</dt>
              <dd>papers</dd>
            </div>
            <div>
              <dt>{catalog.summary.arxivSubjects.toLocaleString()}</dt>
              <dd>arXiv subjects</dd>
            </div>
            <div>
              <dt>{catalog.summary.candidateDirections.toLocaleString()}</dt>
              <dd>unreviewed questions</dd>
            </div>
            <div>
              <dt>{PUBLISHED_METHOD_CANDIDATES.toLocaleString()}</dt>
              <dd>method candidates</dd>
            </div>
          </dl>
          <CorpusExplorer catalog={catalog} />
        </>
      )}
    </div>
  );
}
