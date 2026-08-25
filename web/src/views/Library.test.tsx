import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { makeAtlas } from "../test/fixtures";
import { LibraryView } from "./Library";

const corpus = vi.hoisted(() => ({
  useCorpus: vi.fn(),
}));

vi.mock("../hooks/corpus", () => corpus);

describe("hosted library", () => {
  it("renders ranked corpus matches", () => {
    const atlas = makeAtlas();
    corpus.useCorpus.mockReturnValue({
      active: true,
      matches: [{ paperId: atlas.papers[0].id, rank: 0.7 }],
      total: 1,
      loading: false,
      error: null,
    });

    const markup = renderToStaticMarkup(
      <LibraryView atlas={atlas} query="evidence" onClearQuery={vi.fn()} />,
    );

    expect(markup).toContain("Hosted PostgreSQL full-text search · read only");
    expect(markup).toContain(atlas.papers[0].title);
    expect(markup).toContain("1 collection entry match");
  });

  it("shows hosted loading state", () => {
    corpus.useCorpus.mockReturnValue({
      active: true,
      matches: [],
      total: 0,
      loading: true,
      error: null,
    });

    const markup = renderToStaticMarkup(
      <LibraryView atlas={makeAtlas()} query="evidence" onClearQuery={vi.fn()} />,
    );

    expect(markup).toContain("Searching the hosted corpus");
    expect(markup).toContain('aria-live="polite"');
  });
});
