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

const catalog = {
  schema_version: 1,
  generator_version: "catalog-1",
  status: "corpus-derived",
  corpus: {
    manifest_sha256: "a".repeat(64),
    source_count: 3_148_342,
    month_count: 444,
  },
  coverage: {
    scanned_papers: 3_148_342,
    eligible_direction_papers: 1_562_571,
    scanned_months: 444,
  },
  counts: {
    broad_areas: 1,
    technique_families: 1,
    arxiv_subjects: 1,
    eligible_directions: 1,
    candidate_directions: 1,
  },
  areas: [
    {
      id: "agents",
      label: "agents",
      all_paper_count: 120,
      in_scope_paper_count: 100,
    },
  ],
  techniques: [
    {
      id: "retrieval-and-memory",
      label: "retrieval and memory",
      all_paper_count: 90,
      in_scope_paper_count: 80,
    },
  ],
  subjects: [{ id: "cs.LG", label: "cs.LG", paper_count: 75, primary_paper_count: 60 }],
  directions: [
    {
      id: "direction:1234567890abcdef",
      status: "candidate",
      subject_id: "cs.LG",
      technique_id: "retrieval-and-memory",
      support_count: 42,
      year_count: 8,
      independent_author_groups_at_least: 3,
      npmi: 0.2,
      support_ids: ["arxiv:2401.00001", "arxiv:2501.00002"],
    },
  ],
  notice: "Candidate directions are not reviewed claims.",
};

async function showMobileFilters(page: Page) {
  if ((page.viewportSize()?.width ?? 1_000) > 720) return;
  const toggle = page.getByRole("button", { name: "Show filters" });
  await expect(toggle).toBeVisible();
  await toggle.click();
}

async function mockTinyCloud(page: Page) {
  await page.route(/\/data\/cloud\/index\.json(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/json", json: cloud }),
  );
  await page.route(/\/data\/cloud\/2026-08\.bin(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/octet-stream", body: pointBytes }),
  );
}

test("the corpus catalog exposes subjects, candidate directions, and evidence", async ({
  page,
}) => {
  await mockTinyCloud(page);
  await page.route(/\/data\/catalog\.json(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/json", json: catalog }),
  );
  await page.goto("/#?d=2&k=trpi");
  await showMobileFilters(page);

  const explore = page.getByRole("button", { name: "Explore corpus" });
  await expect(explore).toBeVisible({ timeout: 20_000 });
  await explore.click();
  await expect(
    page.getByRole("region", { name: "Full-corpus taxonomy" }),
  ).toBeVisible();
  await expect(page.getByText("cs.LG", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /cs\.LG/ }).click();
  await expect(page.getByText("cs.LG × retrieval and memory")).toBeVisible();
  await page.getByText("cs.LG × retrieval and memory").click();
  await expect(page.getByText(/not a reviewed claim of novelty/)).toBeVisible();
  await expect(page.getByRole("link", { name: "2401.00001" })).toHaveAttribute(
    "href",
    "https://arxiv.org/abs/2401.00001",
  );
  await expect(
    page.getByText("Candidate directions are not reviewed claims."),
  ).toBeVisible();
});

test("a missing catalog is explicit and leaves curated lenses available", async ({
  page,
}) => {
  await mockTinyCloud(page);
  await page.route(/\/data\/catalog\.json(?:\?.*)?$/, (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.goto("/#?d=2&k=trpi");
  await showMobileFilters(page);

  await expect(page.locator(".catalog-copy")).toContainText(
    "full-corpus taxonomy is temporarily unavailable",
    { timeout: 20_000 },
  );
  await expect(page.getByRole("button", { name: /Broad areas/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Screened briefs/ })).toBeVisible();
});
