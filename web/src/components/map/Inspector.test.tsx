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
});
