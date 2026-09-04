import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

const pointBytes = Buffer.alloc(25);
pointBytes.write("ATLASPT1", 0, "ascii");
pointBytes.writeUInt32LE(1, 8);
pointBytes.writeFloatLE(1, 12);
const pointHash = createHash("sha256").update(pointBytes).digest("hex");
const zeroHash = "0".repeat(64);

const cloud = {
  schema_version: 1,
  source: "arxiv",
  model: "all-minilm",
  model_digest: zeroHash,
  model_revision: "0".repeat(40),
  projection: "anchor-cosine-8-v1",
  point_bytes: 13,
  source_count: 1,
  count: 1,
  counts: { likely: 1, possible: 0, outside: 0 },
  omitted_count: 0,
  omitted_counts: { likely: 0, possible: 0, outside: 0 },
  omitted_sha256: zeroHash,
  foreground_sha256: zeroHash,
  shards: [
    {
      month: "2026-08",
      source_sha256: zeroHash,
      source_count: 1,
      source_counts: { likely: 1, possible: 0, outside: 0 },
      foreground_sha256: zeroHash,
      count: 1,
      counts: { likely: 1, possible: 0, outside: 0 },
      omitted_count: 0,
      omitted_counts: { likely: 0, possible: 0, outside: 0 },
      omitted_ids: [],
      omitted_sha256: zeroHash,
      points: { path: "2026-08.bin", sha256: pointHash, bytes: 25 },
      meta: { path: "2026-08.json", sha256: zeroHash, bytes: 2 },
    },
  ],
};

async function showMobileFilters(page: Page) {
  if ((page.viewportSize()?.width ?? 1_000) > 720) return;
  const toggle = page.getByRole("button", { name: /(?:Show|Hide) filters/ });
  await expect(toggle).toBeVisible({ timeout: 20_000 });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") {
    await toggle.click();
  }
}

async function mockTinyCloud(page: Page) {
  await page.route(/\/data\/cloud\/index\.json(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/json", json: cloud }),
  );
  await page.route(/\/data\/cloud\/2026-08\.bin(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/octet-stream", body: pointBytes }),
  );
}

test("the map keeps corpus catalogs out of its compact filters", async ({ page }) => {
  const catalogs: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (
      url.includes("/data/catalog.json") ||
      url.includes("/data/methods/") ||
      /\/assets\/(?:Catalog|Methods)-[^/]+\.js/.test(url)
    ) {
      catalogs.push(url);
    }
  });
  await mockTinyCloud(page);

  for (const dimension of [2, 3]) {
    await page.goto(`/#?d=${dimension}&k=trpi`);
    await showMobileFilters(page);
    await expect(page.locator(".catalog-copy")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Topics\s+[\d,]+$/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Ideas\s+[\d,]+$/ })).toBeVisible();
  }
  expect(catalogs).toEqual([]);
});
