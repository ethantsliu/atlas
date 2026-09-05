import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas } from "../test/fixtures";
import { CoverageView } from "./Coverage";

vi.mock("../hooks/archive", () => ({
  useArchive: () => ({
    schema_version: 1,
    storage: "github-release",
    retention: "all metadata",
    counts: { all: 10, likely: 4, possible: 3, outside: 3 },
    shards: [
      {
        month: "2024-01",
        path: "2024-01.json.gz",
        sha256: "a".repeat(64),
        bytes: 100,
        days: 2,
        dates: ["2024-01-01", "2024-01-02"],
        counts: { all: 10, likely: 4, possible: 3, outside: 3 },
      },
    ],
  }),
}));

describe("CoverageView", () => {
  it("separates the arXiv map corpus from Atlas reading-depth coverage", () => {
    const atlas = makeAtlas();
    const html = renderToStaticMarkup(<CoverageView atlas={atlas} />);

    expect(html).toContain("arXiv map corpus");
    expect(html).toContain("arXiv source records");
    expect(html).toContain("not counted as read, reviewed, or full text above");
    expect(html).toContain(
      `aria-label="Reading depth for ${atlas.coverage.collection_entries.toLocaleString()} paper profiles"`,
    );
    expect(html).toContain(">10<");
    expect(html).not.toContain("likely ML");
    expect(html).not.toContain("possible ML");
    expect(html).not.toContain("archive context");
    expect(html).not.toContain("classified contextual records");
  });
});
