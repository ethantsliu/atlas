import { useId, useMemo, useState } from "react";
import { labelOf } from "../../lib/text";
import type { CompetingPaper } from "../../types";

const INITIAL_COUNT = 8;

function Provenance({ competitor }: { competitor: CompetingPaper }) {
  if (
    !competitor.provenance_status &&
    !competitor.source_kind &&
    !competitor.source_version &&
    !competitor.source_date &&
    !competitor.checked_at
  ) {
    return null;
  }
  return (
    <small className="brief-competitor-provenance">
      <strong
        className={`competitor-provenance-status ${competitor.provenance_status ?? "unknown"}`}
      >
        {competitor.provenance_status === "version-verified"
          ? "Revision verified"
          : "Legacy / unversioned"}
      </strong>
      {[
        competitor.source_kind && labelOf(competitor.source_kind),
        competitor.source_version,
        competitor.source_date && `source dated ${competitor.source_date}`,
        competitor.checked_at && `checked ${competitor.checked_at}`,
      ]
        .filter(Boolean)
        .join(" · ")}
    </small>
  );
}

export function Landscape({ competitors }: { competitors: CompetingPaper[] }) {
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return competitors;
    return competitors.filter((competitor) =>
      [competitor.title, competitor.relationship, competitor.difference]
        .join(" ")
        .toLocaleLowerCase()
        .includes(needle),
    );
  }, [competitors, query]);
  const visible = expanded || query ? filtered : filtered.slice(0, INITIAL_COUNT);

  return (
    <>
      <div className="landscape-tools">
        <label htmlFor={searchId}>
          <span>Search literature</span>
          <input
            id={searchId}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Title, relationship, or difference"
          />
        </label>
        <span aria-live="polite">
          {filtered.length} of {competitors.length} papers
        </span>
      </div>
      <div className="landscape">
        {visible.map((competitor) => (
          <a
            href={competitor.url}
            target="_blank"
            rel="noreferrer"
            key={competitor.canonical_id}
          >
            <span>{competitor.relationship}</span>
            <b>{competitor.title}</b>
            <p>{competitor.difference}</p>
            <Provenance competitor={competitor} />
          </a>
        ))}
      </div>
      {!query && filtered.length > INITIAL_COUNT && (
        <button
          className="landscape-toggle"
          type="button"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
        >
          {expanded ? "Show fewer papers" : `Show all ${filtered.length} papers`}
        </button>
      )}
      {filtered.length === 0 && <p className="landscape-empty">No papers match.</p>}
    </>
  );
}
