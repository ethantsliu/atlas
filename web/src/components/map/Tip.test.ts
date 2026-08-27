import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { GraphNode } from "../../types";
import { nodeTip } from "./Tip";

describe("2D node tooltip", () => {
  it("assigns hostile paper titles as text instead of HTML", () => {
    const node = {
      kind: "paper",
      label: '<img src=x onerror="globalThis.pwned=true">',
    } as GraphNode;
    const markup = renderToStaticMarkup(nodeTip(node));

    expect(markup).toContain(
      "Paper · &lt;img src=x onerror=&quot;globalThis.pwned=true&quot;&gt;",
    );
    expect(markup).not.toContain("<img");
  });
});
