import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { DiscoveryQueue } from "../../lib/discovery";
import { candidateLabel, DiscoveryQueueList } from "./Discovery";

const candidate = {
  id: `idea:${"d".repeat(64)}`,
  digest: "e".repeat(64),
  reviewStatus: "unreviewed" as const,
  identity: {
    target: "evaluation",
    intervention: "retrieval and memory",
    mechanism: "cross-paper topic-technique co-occurrence",
    outcome: "controlled falsification signal",
  },
  supportIds: ["arxiv:2401.00001", "arxiv:2401.00002"],
};

const queue: DiscoveryQueue = {
  source: {
    runId: 33_827_765_332,
    artifactId: 9_923_640_228,
    artifactSha256: "a".repeat(64),
    corpusDigest: "b".repeat(64),
    manifestSha256: "c".repeat(64),
    manifestPapers: 3_148_342,
    loadedPapers: 1_612_535,
    skippedOutside: 1_535_807,
  },
  notice:
    "Machine-generated cross-paper combinations queued for human review. They are not screened briefs, recommendations, novelty findings, or feasibility assessments.",
  candidates: [candidate],
};

describe("discovery review queue presentation", () => {
  it("never presents provisional candidates as screened or ranked briefs", () => {
    const markup = renderToStaticMarkup(<DiscoveryQueueList queue={queue} query="" />);

    expect(candidateLabel(candidate)).toBe("retrieval and memory × evaluation");
    expect(markup).toContain("1 unreviewed discovery");
    expect(markup).toContain("not part of the curated brief count");
    expect(markup).toContain("novelty and feasibility not assessed");
    expect(markup).toContain("3,148,342-paper manifest");
    expect(markup).toContain("1,612,535 records in its configured scope");
    expect(markup).toContain("actions/runs/33827765332");
    expect(markup).not.toContain("card-score");
    expect(markup).not.toMatch(/#[0-9]+ portfolio/);
  });

  it("filters independently from curated Atlas ideas", () => {
    const markup = renderToStaticMarkup(
      <DiscoveryQueueList queue={queue} query="unrelated" />,
    );

    expect(markup).toContain("No review-queue candidates match this search");
  });
});
