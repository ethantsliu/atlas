import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const viewports = [
  { width: 375, height: 812 },
  { width: 720, height: 900 },
  { width: 1000, height: 900 },
];

async function scan(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}

function mapStatus(page: Page) {
  return page.locator(".map-layout > [role=status]").first();
}

for (const viewport of viewports) {
  test(`${viewport.width}px layout has no horizontal page overflow`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByText("Atlas", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Choose a visible graph node")).toBeAttached();
    const titleBox = await page.locator(".brand-copy strong").boundingBox();
    const captionBox = await page.locator(".brand-copy span").boundingBox();
    expect(titleBox).not.toBeNull();
    expect(captionBox).not.toBeNull();
    expect(titleBox!.y + titleBox!.height).toBeLessThanOrEqual(captionBox!.y + 1);

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(hasOverflow).toBe(false);
    if (viewport.width <= 720) {
      const graphBox = await page
        .getByLabel(/Interactive (3D )?research graph/)
        .boundingBox();
      expect(graphBox).not.toBeNull();
      expect(graphBox!.width).toBeGreaterThanOrEqual(viewport.width - 2);
    }

    for (const view of ["Daily", "Library", "Briefs"]) {
      await page.getByRole("button", { name: view, exact: true }).click();
      const viewOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      expect(viewOverflow).toBe(false);
    }
  });
}

test("tablet header keeps the atlas search usable", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/");

  const searchBox = await page.locator(".search").boundingBox();
  const inputBox = await page.getByLabel("Search the atlas").boundingBox();
  expect(searchBox?.width).toBeGreaterThan(300);
  expect(inputBox?.width).toBeGreaterThan(200);
});

test("map and semantic fallbacks pass an automated accessibility scan", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByLabel(/Interactive (3D )?research graph/)).toBeVisible();
  await page.waitForTimeout(250);
  expect(errors).toEqual([]);
  await scan(page);
});

test("map remains usable without WebGL2", async ({ page }) => {
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
  await page.goto("/");

  const graph = page.getByLabel("Interactive research graph");
  await expect(graph).toContainText("2D semantic compatibility view");
  await expect(graph.locator("canvas")).toBeVisible();
  await graph.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByLabel("Choose a visible graph node")).not.toHaveValue("");
});

test("dark mode follows the system and remembers a choice", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const lightMode = page.getByRole("button", { name: "Use light mode" });
  await expect(lightMode).toHaveAttribute("aria-pressed", "true");
  await scan(page);

  await lightMode.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("button", { name: "Use dark mode" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("atlas-theme")))
    .toBe("light");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("connection isolation toggles back to the full map", async ({ page }) => {
  await page.goto("/");
  const status = mapStatus(page);
  await expect(status).toHaveText(/\d+ visible graph nodes available\./);
  const fullState = await status.textContent();
  expect(fullState).toBeTruthy();
  const picker = page.getByLabel("Choose a visible graph node");
  const firstNode = await picker.locator("option").nth(1).getAttribute("value");
  expect(firstNode).toBeTruthy();
  await picker.selectOption(firstNode!);

  const isolate = page.getByRole("button", { name: "Isolate connections" });
  await expect(isolate).toHaveAttribute("aria-pressed", "false");
  await isolate.click();
  const unisolate = page.getByRole("button", { name: "Unisolate connections" });
  await expect(unisolate).toHaveAttribute("aria-pressed", "true");
  await expect(status).not.toHaveText(fullState!);

  await unisolate.click();
  await expect(
    page.getByRole("button", { name: "Isolate connections" }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(status).toHaveText(fullState!);
});

test("paper lens and arrow-key graph navigation stay concise", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/");
  const filters = page.locator(".filters");
  const showFilters = filters.locator(".mobile-filter-toggle");
  if ((page.viewportSize()?.width ?? 1000) <= 720) {
    await expect(showFilters).toBeVisible();
    await showFilters.tap();
    await expect(showFilters).toHaveAttribute("aria-expanded", "true");
  }
  await expect(filters.getByText("Paper", { exact: true })).toBeVisible();
  await expect(filters).not.toContainText("Paper / context");
  const paperLens = filters.getByRole("button", { name: /Paper\s+2205/ });
  await paperLens.click();
  await expect(paperLens).toHaveAttribute("aria-pressed", "true");
  await expect(mapStatus(page)).toContainText("2,316 visible graph nodes available", {
    timeout: 20_000,
  });

  const graph = page.getByLabel(/Interactive (3D )?research graph/);
  const picker = page.getByLabel("Choose a visible graph node");
  await expect(graph.locator("canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: /Reset (3D )?view/ })).toBeVisible();
  await expect(graph).toContainText(/drag (rotates|pans)/);
  await graph.focus();
  await page.keyboard.press("ArrowRight");
  await expect(picker).not.toHaveValue("");
  await expect(graph).toBeFocused();
});

test("daily discovery proves intake coverage and preserves all relevant papers", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Daily", exact: true }).click();

  await expect(page.getByText("submissions scanned", { exact: true })).toBeVisible();
  await expect(page.getByText("Complete", { exact: true })).toBeVisible();
  await expect(
    page.getByText("interest shortlist", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator(".daily-card")).toHaveCount(30);
  await expect(page.getByLabel("Paper result pages")).toContainText("Page 1 of 2");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".daily-card")).toHaveCount(10);
  await page.getByRole("button", { name: "All relevant", exact: true }).click();
  await expect(page.locator(".daily-card")).toHaveCount(30);
  await expect(page.getByRole("status")).toContainText("276 daily papers available");
  await expect(page.getByLabel("Paper result pages")).toContainText("Page 1 of 10");
  await scan(page);
});

test("root loading is announced and a failed request can retry", async ({ page }) => {
  let unavailable = true;
  await page.route("**/data/atlas.json", async (route) => {
    if (unavailable) {
      await route.fulfill({ status: 503, body: "Unavailable" });
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Atlas request failed (503)");
  unavailable = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("status")).toContainText("Building the atlas");
  await expect(page.getByText("Atlas", { exact: true })).toBeVisible();
});

test("search views announce empty results and offer working resets", async ({
  page,
}) => {
  await page.goto("/");
  const search = page.getByLabel("Search the atlas");
  await search.fill("zzzz-no-results-zzzz");

  await expect(page.getByText(/No graph nodes match/)).toBeVisible();
  await expect(mapStatus(page)).toContainText("0 visible graph nodes match");
  await page.getByRole("button", { name: "Reset map" }).click();
  await expect(search).toHaveValue("");
  await expect(page.getByLabel("Choose a visible graph node")).toBeAttached();

  await page.getByRole("button", { name: "Library" }).click();
  await search.fill("zzzz-no-results-zzzz");
  await expect(page.getByText(/No entries match/)).toBeVisible();
  await expect(page.getByRole("status")).toContainText("0 collection entries match");
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(
    page.getByRole("table", { name: "Collection entry library" }),
  ).toBeVisible();
  await scan(page);

  await page.getByRole("button", { name: "Briefs" }).click();
  await search.fill("zzzz-no-results-zzzz");
  await expect(page.getByText(/No briefs match/)).toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "0 research or blog briefs match",
  );
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(page.getByRole("button", { name: "Open brief" }).first()).toBeVisible();
  await scan(page);
});

test("brief dialog exposes provenance, traps focus, and restores focus", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Briefs" }).click();
  const trigger = page.getByRole("button", { name: "Open brief" }).first();
  await trigger.click();

  const dialog = page.getByRole("dialog", { name: /.+/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Evidence basis")).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Close research brief" }),
  ).toBeFocused();
  await scan(page);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("alternate-source paper dialog passes an accessibility scan", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Library" }).click();
  await page.getByLabel("Search the atlas").fill("GENERALIZATION MECHANICS");
  await page.getByRole("button", { name: /Open GENERALIZATION MECHANICS/i }).click();

  const dialog = page.getByRole("dialog", { name: /GENERALIZATION MECHANICS/i });
  await expect(dialog.getByLabel("Pinned reading source")).toBeVisible();
  await expect(dialog.getByText("HTML source SHA-256", { exact: true })).toBeVisible();
  await scan(page);
});

test("researched briefs are ranked by one-decimal feasibility", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Briefs" }).click();

  const scoreCards = page.locator(".featured-briefs .card-score");
  await expect(scoreCards.first()).toBeVisible();
  const scoreLabels = await scoreCards.allTextContents();
  const scores = scoreLabels.map((label) => Number.parseFloat(label));
  expect(scores.length).toBeGreaterThan(1);
  expect(scores).toEqual([...scores].sort((left, right) => right - left));
  expect(scoreLabels.every((label) => /^\d+\.\d feasibility$/.test(label))).toBe(true);
});

test("cross-scale calibration exposes its complete validation protocol", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Briefs" }).click();

  const card = page
    .locator(".brief-card")
    .filter({ hasText: "Prospective cross-scale calibration" });
  await card.getByRole("button", { name: "Open brief" }).click();

  const dialog = page.getByRole("dialog", {
    name: /Prospective cross-scale calibration/,
  });
  await expect(dialog.getByText("What counts as learning signal")).toBeVisible();
  await expect(dialog.getByText("Human in the loop")).toBeVisible();
  await expect(dialog.getByText("Scaling claim protocol")).toBeVisible();
  await expect(dialog.getByText("Decisive experiment")).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Primary outcome", exact: true }),
  ).toBeVisible();
  await expect(dialog.getByText("Analysis", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Claim-blocking falsifiers")).toBeVisible();
  await expect(dialog).not.toContainText("undefined");
});

test("insight visualizations provide inspectable data tables", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Insights" }).click();
  await expect(
    page.getByRole("heading", { name: "Topic × technique density" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Corpus × full-text coverage" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Idea feasibility factors" }),
  ).toBeVisible();
  const tableToggles = page.getByText("View data table");
  await expect(tableToggles).toHaveCount(10);
  for (const toggle of await tableToggles.all()) await toggle.click();
  await expect(page.getByRole("table")).toHaveCount(10);
  await scan(page);
});

test("coverage reports partial extraction state honestly", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Coverage" }).click();

  const partialStatus = page.getByText(/^Partial Text\s+[\d,]+$/);
  if ((await partialStatus.count()) > 0) {
    await expect(partialStatus).toBeVisible();
    await expect(page.getByText(/partial extracts remain visible/i)).toBeVisible();
  } else {
    await expect(
      page.getByText(/no partial extracts remain in the current ledger/i),
    ).toBeVisible();
  }
});
