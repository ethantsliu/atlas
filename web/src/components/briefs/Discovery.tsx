import { useEffect, useMemo, useState } from "react";
import { ExternalLink, ScanSearch } from "lucide-react";
import {
  fetchDiscoveryQueue,
  type DiscoveryCandidate,
  type DiscoveryQueue,
} from "../../lib/discovery";
import "./Discovery.css";

const INITIAL_ROWS = 12;

function includes(candidate: DiscoveryCandidate, query: string): boolean {
  if (!query) return true;
  const identity = candidate.identity;
  return [identity.intervention, identity.target, identity.mechanism, identity.outcome]
    .join(" ")
    .toLocaleLowerCase()
    .includes(query);
}

export function candidateLabel(candidate: DiscoveryCandidate): string {
  return `${candidate.identity.intervention} × ${candidate.identity.target}`;
}

export function DiscoveryQueueList({
  queue,
  query,
}: {
  queue: DiscoveryQueue;
  query: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const term = query.trim().toLocaleLowerCase();
  const matching = useMemo(
    () => queue.candidates.filter((candidate) => includes(candidate, term)),
    [queue.candidates, term],
  );
  const visible = expanded || term ? matching : matching.slice(0, INITIAL_ROWS);
  const source = queue.source;

  return (
    <section className="discovery-queue" aria-labelledby="discovery-queue-title">
      <header className="brief-section-head">
        <span>
          <ScanSearch size={13} /> {queue.candidates.length} unreviewed discovery
          candidates
        </span>
        <h2 id="discovery-queue-title">
          Machine-generated combinations awaiting review
        </h2>
        <p>
          This is a separate review queue, not part of the Atlas idea count. It has no
          feasibility score, recommendation, or finding of novelty. The run was bound to
          a {source.manifestPapers.toLocaleString()}-paper manifest and evaluated{" "}
          {source.loadedPapers.toLocaleString()} records in its configured scope.
        </p>
        <a
          className="discovery-provenance"
          href={`https://github.com/ethantsliu/atlas/actions/runs/${source.runId}`}
          target="_blank"
          rel="noreferrer"
        >
          Validated run {source.runId} · artifact {source.artifactId}
          <ExternalLink size={12} />
        </a>
      </header>
      {matching.length === 0 ? (
        <p className="discovery-empty">No review-queue candidates match this search.</p>
      ) : (
        <ul className="discovery-list" aria-label="Unreviewed discovery candidates">
          {visible.map((candidate) => (
            <li key={candidate.id}>
              <details>
                <summary>
                  <b>{candidateLabel(candidate)}</b>
                  <span>Unreviewed · novelty and feasibility not assessed</span>
                </summary>
                <p>
                  Proposed evidence target: {candidate.identity.outcome}. Generation
                  mechanism: {candidate.identity.mechanism}.
                </p>
                <small>Corpus support used to generate this candidate:</small>
                <ul>
                  {candidate.supportIds.map((id) => {
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
                <code title="Candidate digest">{candidate.digest.slice(0, 16)}</code>
              </details>
            </li>
          ))}
        </ul>
      )}
      {!term && matching.length > INITIAL_ROWS && (
        <button
          type="button"
          className="discovery-more"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded
            ? "Show first 12"
            : `Show all ${matching.length.toLocaleString()} unreviewed candidates`}
        </button>
      )}
      <p className="discovery-notice">
        These candidates are unreviewed and are not recommendations, novelty findings,
        or feasibility assessments.
      </p>
    </section>
  );
}

export function DiscoveryReviewQueue({ query }: { query: string }) {
  const [queue, setQueue] = useState<DiscoveryQueue | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchDiscoveryQueue(controller.signal)
      .then(setQueue)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Discovery queue failed");
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return (
      <section className="discovery-queue unavailable" role="status">
        <b>Unreviewed discovery queue unavailable</b>
        <p>{error}</p>
      </section>
    );
  }
  if (!queue) {
    return (
      <section className="discovery-queue unavailable" role="status" aria-busy="true">
        Loading the separate unreviewed discovery queue…
      </section>
    );
  }
  return <DiscoveryQueueList queue={queue} query={query} />;
}
