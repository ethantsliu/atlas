import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { createGraphNodes } from "../../lib/graph";
import { makeAtlas, makeLayout } from "../../test/fixtures";
import { Inspector } from "./Inspector";

describe("Inspector", () => {
  it("shows at most six qualified embedding neighbors", () => {
    const atlas = makeAtlas({ layout: makeLayout() });
    const nodes = createGraphNodes(atlas, 1);
    const selected = nodes[0];
    atlas.layout!.neighbors[selected.id] = nodes
      .slice(1)
      .concat(nodes.slice(1, 3))
      .map((node, index) => ({ id: node.id, score: 0.9 - index / 100 }));

    const html = renderToStaticMarkup(
      <Inspector
        node={selected}
        cloud={null}
        hasNodes
        atlas={atlas}
        focused={false}
        onFocus={vi.fn()}
        onSelectNode={vi.fn()}
        onClose={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(html).toContain("Exact cosine neighbors in the pinned embedding space");
    expect(html).toContain("not a citation or evidence link");
    expect((html.match(/cosine 0\./g) ?? []).length).toBeLessThanOrEqual(6);
    expect(html.indexOf("Isolate connections")).toBeLessThan(
      html.indexOf("Semantically nearby"),
    );
  });

  it("labels an automatic screening idea and exposes its caveat", () => {
    const atlas = makeAtlas();
    const idea = createGraphNodes(atlas, 1).find((node) => node.kind === "idea")!;
    const html = renderToStaticMarkup(
      <Inspector
        node={idea}
        cloud={null}
        hasNodes
        atlas={atlas}
        focused={false}
        onFocus={vi.fn()}
        onSelectNode={vi.fn()}
        onClose={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(html).toContain("Screening candidate");
    expect(html).toContain("Automatically synthesized from corpus routes");
    expect(html).not.toContain("cross-paper");
  });

  it("presents legacy provenance records as Papers", () => {
    const atlas = makeAtlas();
    atlas.papers[0] = {
      ...atlas.papers[0],
      record_kind: "non_paper_context",
      reading_depth: "context",
    };
    const paper = createGraphNodes(atlas, 1).find((node) => node.kind === "paper")!;
    const html = renderToStaticMarkup(
      <Inspector
        node={paper}
        cloud={null}
        hasNodes
        atlas={atlas}
        focused={false}
        onFocus={vi.fn()}
        onSelectNode={vi.fn()}
        onClose={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(html).toContain("<b>Paper</b>");
    expect(html).not.toContain("Context");
    expect(html).not.toContain(">context<");
  });

  it("shows a standalone historical paper without connection controls", () => {
    const html = renderToStaticMarkup(
      <Inspector
        node={null}
        cloud={{
          id: "2001.00001",
          title: "A Historical Paper",
          url: "https://arxiv.org/abs/2001.00001",
          published: "2020-01-02T00:00:00Z",
          scope: "likely",
        }}
        hasNodes
        atlas={makeAtlas()}
        focused={false}
        onFocus={vi.fn()}
        onSelectNode={vi.fn()}
        onClose={vi.fn()}
        onOpenPaper={vi.fn()}
      />,
    );

    expect(html).toContain("A Historical Paper");
    expect(html).toContain("2020-01-02");
    expect(html).toContain("View on arXiv");
    expect(html).not.toContain("Isolate connections");
    expect(html).not.toContain('role="dialog"');
  });
});
