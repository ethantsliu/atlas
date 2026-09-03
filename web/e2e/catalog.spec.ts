import { expect, test } from "@playwright/test";

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

test("the corpus catalog exposes subjects, candidate directions, and evidence", async ({
  page,
}) => {
  await page.route(/\/data\/catalog\.json(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/json", json: catalog }),
  );
  await page.route(/\/data\/cloud\/.*\.bin(?:\?.*)?$/, (route) => route.abort());
  await page.goto("/#?d=2&k=trpi");

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
  await page.route(/\/data\/catalog\.json(?:\?.*)?$/, (route) =>
    route.fulfill({ status: 503 }),
  );
  await page.goto("/#?d=2&k=trpi");

  await expect(page.locator(".catalog-copy")).toContainText(
    "full-corpus taxonomy is temporarily unavailable",
    { timeout: 20_000 },
  );
  await expect(page.getByRole("button", { name: /Broad areas/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Screened briefs/ })).toBeVisible();
});
