/// <reference types="vite/client" />

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import source from "./Methods.tsx?raw";
import Methods from "./Methods";
import { METHOD_CANDIDATE_NOTICE, METHOD_RELEASE_NOTICE } from "../../lib/methods";

describe("method candidate browser", () => {
  it("does not start a request during an unopened static render", () => {
    const fetcher = vi.spyOn(globalThis, "fetch");
    const markup = renderToStaticMarkup(<Methods />);

    expect(fetcher).not.toHaveBeenCalled();
    expect(markup).toContain("Loading method index");
    fetcher.mockRestore();
  });

  it("uses the candidate-only language and a delayed three-character search", () => {
    expect(METHOD_CANDIDATE_NOTICE).toBe(
      "Lexical phrases extracted from abstracts; not reviewed techniques, novelty claims, evidence of effectiveness, or recommendations.",
    );
    expect(source).toContain("Corpus-extracted candidate");
    expect(source).toContain("Most frequently supported");
    expect(source).toContain("Search extracted phrases (3+ characters)");
    expect(source).toContain("METHOD_QUERY_DELAY_MS");
    expect(source).toContain("controller.abort()");
    expect(METHOD_RELEASE_NOTICE).toBe(
      "Evidence spans are available only in the immutable full release download.",
    );
    expect(source).toContain("Download verified full candidate evidence");
    expect(source).not.toContain("quality");
    expect(source).not.toContain("effective method");
  });

  it("keeps extracted phrases outside graph data", () => {
    expect(source).not.toContain("GraphNode");
    expect(source).not.toContain("scene");
    expect(source).not.toContain("pick");
  });
});
