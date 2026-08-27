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
  it("presents historical scope as one Paper aggregate", () => {
    const html = renderToStaticMarkup(<CoverageView atlas={makeAtlas()} />);

    expect(html).toContain("Historical Papers");
    expect(html).toContain("historical Papers");
    expect(html).toContain(">10<");
    expect(html).not.toContain("likely ML");
    expect(html).not.toContain("possible ML");
    expect(html).not.toContain("archive context");
    expect(html).not.toContain("classified contextual records");
  });
});
