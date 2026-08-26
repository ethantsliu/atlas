import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { makeAtlas, makeLayout } from "../src/test/fixtures";
import type { AtlasCore, PaperBundle } from "../src/lib/payload";

function splitAtlas(): { core: AtlasCore; body: string } {
  const { papers, ...rest } = makeAtlas({ layout: makeLayout() });
  const paperIds = new Set(papers.map((paper) => paper.id));
  const layout = rest.layout! as unknown as Record<string, unknown>;
  const coreLayout = { ...layout };
  const paperLayout = {
    positions: {},
    neighbors: {},
    node_clusters: {},
  } as PaperBundle["layout"];
  for (const field of ["positions", "neighbors", "node_clusters"] as const) {
    const entries = Object.entries(layout[field] as Record<string, unknown>);
    coreLayout[field] = Object.fromEntries(entries.filter(([id]) => !paperIds.has(id)));
    (paperLayout as unknown as Record<string, unknown>)[field] = Object.fromEntries(
      entries.filter(([id]) => paperIds.has(id)),
    );
  }
  const bundle: PaperBundle = { schema_version: 1, papers, layout: paperLayout };
  const body = `${JSON.stringify(bundle)}\n`;
  const sha256 = createHash("sha256").update(body).digest("hex");
  return {
    body,
    core: {
      schema_version: 2,
      ...rest,
      layout: coreLayout,
      paper_asset: {
        schema_version: 1,
        path: `/data/papers/${sha256}.json`,
        sha256,
        bytes: Buffer.byteLength(body),
        paper_count: papers.length,
      },
    } as unknown as AtlasCore,
  };
}

test("compatibility mode skips the 3D runtime", async ({ page }) => {
  const requests: string[] = [];
  const { core, body } = splitAtlas();
  page.on("request", (request) => requests.push(request.url()));
  await page.route("**/data/atlas.json", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(core) }),
  );
  await page.route("**/data/papers/*.json", (route) =>
    route.fulfill({ contentType: "application/json", body }),
  );
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type === "webgl2") return null;
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
  });

  await page.goto("/#?k=tri");
  await expect(
    page.getByLabel("Interactive research graph").locator("canvas"),
  ).toBeVisible();
  expect(
    requests.some((url) => /(?:\/Fallback\.tsx|\/Fallback-[\w-]+\.js)/.test(url)),
  ).toBe(true);
  expect(
    requests.some((url) =>
      /(?:\/Space\.tsx|\/Space-[\w-]+\.js|react-force-graph-3d|three-spritetext)/.test(
        url,
      ),
    ),
  ).toBe(false);
});
