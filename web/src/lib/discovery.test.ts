import { describe, expect, it, vi } from "vitest";
import { fetchDiscoveryQueue, readDiscoveryQueue } from "./discovery";

function fixture() {
  return {
    schema_version: 1,
    generator_version: "discovery-browser-1",
    status: "provisional",
    source: {
      run_id: 33_827_765_332,
      artifact_id: 9_923_640_228,
      artifact_sha256: "a".repeat(64),
      generator_version: "discover-2",
      corpus_digest: "b".repeat(64),
      manifest_sha256: "c".repeat(64),
      manifest_papers: 3_148_342,
      loaded_papers: 1_612_535,
      skipped_outside: 1_535_807,
    },
    count: 1,
    review_gate: {
      automatic_promotion: false,
      required_receipt: "declared-human-review",
      note: "Promotion requires a declared review receipt bound to the candidate digest; this receipt is not authenticated human proof, and provenance hashes are not related-work evidence.",
    },
    notice:
      "Machine-generated cross-paper combinations queued for human review. They are not screened briefs, recommendations, novelty findings, or feasibility assessments.",
    candidates: [
      {
        id: `idea:${"d".repeat(64)}`,
        digest: "e".repeat(64),
        review_status: "unreviewed",
        identity: {
          target: "evaluation",
          intervention: "retrieval and memory",
          mechanism: "cross-paper topic-technique co-occurrence",
          outcome: "controlled falsification signal",
        },
        support_ids: ["arxiv:2401.00001", "arxiv:2401.00002"],
      },
    ],
  };
}

describe("discovery review queue", () => {
  it("reads only the separate unreviewed contract", () => {
    const queue = readDiscoveryQueue(fixture());

    expect(queue?.source.manifestPapers).toBe(3_148_342);
    expect(queue?.candidates[0].reviewStatus).toBe("unreviewed");
    expect(queue?.candidates[0].identity.intervention).toBe("retrieval and memory");
  });

  it("rejects promotion, count drift, and malformed provenance", () => {
    const promoted = fixture();
    promoted.candidates[0].review_status = "reviewed";
    expect(readDiscoveryQueue(promoted)).toBeNull();

    const stale = fixture();
    stale.count = 2;
    expect(readDiscoveryQueue(stale)).toBeNull();

    const malformed = fixture();
    malformed.source.artifact_sha256 = "missing";
    expect(readDiscoveryQueue(malformed)).toBeNull();
  });

  it("loads the same-origin static queue", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(fixture()),
    });

    await expect(
      fetchDiscoveryQueue(undefined, fetcher, "/atlas/"),
    ).resolves.toMatchObject({ candidates: [{ reviewStatus: "unreviewed" }] });
    expect(fetcher).toHaveBeenCalledWith(
      "/atlas/data/discovery.json",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });
});
