import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ClusterRegion } from "../../lib/clusters";
import { ClusterPanel } from "./Clusters";
import { RegionOverlay } from "./Regions";

const region: ClusterRegion = {
  id: "envs",
  label: "rl environments",
  centroid: [0, 0, 0],
  count: 37,
  radius: 12,
  color: "#547861",
  terms: ["generation", "validation"],
};

describe("cluster views", () => {
  it("mirrors region identity and counts in a semantic table", () => {
    const html = renderToStaticMarkup(
      <ClusterPanel regions={[region]} activeId="envs" onPick={() => undefined} open />,
    );
    expect(html).toContain("Coarse embedding neighborhoods in the current atlas view");
    expect(html).toContain("rl environments");
    expect(html).toContain("generation · validation");
    expect(html).toContain("37");
    expect(html).toContain("<button");
  });

  it("marks projected visual labels as an accessibility-hidden mirror", () => {
    const html = renderToStaticMarkup(
      <RegionOverlay
        points={[{ region, x: 200, y: 160, depth: 0 }]}
        view={{ width: 500, height: 400, scale: 1 }}
      />,
    );
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("rl environments");
    expect(html).not.toContain("button");
  });

  it("distinguishes an active region from ambient geography", () => {
    const html = renderToStaticMarkup(
      <RegionOverlay
        points={[{ region, x: 200, y: 160, depth: 0 }]}
        view={{ width: 500, height: 400, scale: 1, activeId: "envs" }}
      />,
    );
    expect(html).toContain('class="region-label active"');
  });
});
