import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { has3d } from "./capability";
import { fullNodes, mapStatus } from "./map";

const viewports = [
  { width: 375, height: 812 },
  { width: 720, height: 900 },
  { width: 1000, height: 900 },
];

const corePath = "/#?k=tri";
const cloudPath = "/#?d=3";

async function scan(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}

for (const viewport of viewports) {
  test(`${viewport.width}px layout has no horizontal page overflow`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto(corePath);
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
  await page.goto(corePath);

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
  await page.goto(corePath);
  await expect(page.getByLabel(/Interactive (3D )?research graph/)).toBeVisible();
  await page.evaluate(() => document.fonts.load('16px "Libre Baskerville Variable"'));
  const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(family).toContain("Libre Baskerville Variable");
  const remoteFonts = await page.evaluate(() =>
    performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((url) => /fonts\.(googleapis|gstatic)\.com/.test(url)),
  );
  expect(remoteFonts).toEqual([]);
  await page.waitForTimeout(250);
  expect(errors).toEqual([]);
  await scan(page);
});

test("map remains usable without WebGL2", async ({ page }) => {
  let cloudRequests = 0;
  page.on("request", (request) => {
    if (/\/data\/cloud\/index\.json(?:\?.*)?$/.test(request.url())) {
      cloudRequests += 1;
    }
  });
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
  await expect(graph).toContainText("2D overview · semantic", {
    timeout: 20_000,
  });
  await expect(graph.locator("canvas:not(.cloud-plane)")).toBeVisible({
    timeout: 20_000,
  });
  await expect(mapStatus(page)).toHaveText("3,999 visible graph nodes available.", {
    timeout: 30_000,
  });
  expect(cloudRequests).toBe(1);
  await graph.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByLabel("Choose a visible graph node")).not.toHaveValue("");
});

test("historical paper loading can recover without resetting the map", async ({
  page,
}) => {
  test.setTimeout(90_000);
  let attempts = 0;
  let rejectCloud = true;
  let resumePapers = () => {};
  const paperGate = new Promise<void>((resolve) => {
    resumePapers = resolve;
  });
  await page.route(/\/data\/papers\/[a-f0-9]{64}\.json(?:\?.*)?$/, async (route) => {
    await paperGate;
    await route.continue();
  });
  await page.route(/\/data\/cloud\/index\.json(?:\?.*)?$/, async (route) => {
    attempts += 1;
    if (rejectCloud) {
      await route.fulfill({ status: 503, body: "Unavailable" });
      return;
    }
    await route.continue();
  });

  await page.goto(cloudPath);
  const available = await has3d(page);
  if (!available) resumePapers();
  test.skip(!available, "Historical recovery requires WebGL2");
  const alert = page.getByRole("alert").filter({
    hasText: "Historical papers unavailable: Paper cloud request failed (503)",
  });
  await expect(page.getByText("Loading papers…", { exact: true })).toBeVisible();
  await expect(alert).toHaveCount(0);
  resumePapers();
  await expect(alert).toBeVisible({ timeout: 20_000 });
  await expect(page.getByLabel(/Interactive (3D )?research graph/)).toBeVisible();

  const picker = page.getByLabel("Choose a visible graph node");
  await expect(picker).toHaveAttribute("role", "combobox", { timeout: 20_000 });
  await picker.fill("pretraining");
  await page.getByRole("option", { name: /Topic\s+pretraining/i }).click();
  const inspector = page.locator("#map-inspector");
  await expect(inspector.getByRole("heading", { name: "pretraining" })).toBeVisible();

  const graph = page.getByLabel(/Interactive (3D )?research graph/);
  const retry = page.getByRole("button", { name: "Retry historical papers" });
  rejectCloud = false;
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(graph).toBeFocused();
  await expect(alert).toHaveCount(0);
  await expect(page.locator(".filters")).toContainText(
    "papers mapped by semantic similarity",
    {
      timeout: 30_000,
    },
  );
  expect(attempts).toBeGreaterThan(1);
  await expect(graph).toBeFocused();
  await expect(inspector.getByRole("heading", { name: "pretraining" })).toBeVisible();
});

test("dark mode follows the system and remembers a choice", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(corePath);

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
  test.setTimeout(90_000);
  await page.goto(cloudPath);
  const status = mapStatus(page);
  const fullState = await fullNodes(page);
  const fullCount = Number(fullState.match(/[\d,]+/)?.[0].replaceAll(",", ""));
  const picker = page.getByLabel("Choose a visible graph node");
  await picker.fill("pretraining");
  await page.getByRole("option", { name: /Topic\s+pretraining/i }).click();
  const fullUrl = page.url();

  const isolate = page.getByRole("button", { name: "Isolate connections" });
  await expect(isolate).toHaveAttribute("aria-pressed", "false");
  await isolate.click();
  const unisolate = page.getByRole("button", { name: "Unisolate connections" });
  await expect(unisolate).toHaveAttribute("aria-pressed", "true");
  await expect(status).not.toHaveText(fullState!);
  await expect.poll(() => new URL(page.url()).hash).toContain("x=");
  const isolatedCount = Number(
    (await status.textContent())?.match(/[\d,]+/)?.[0].replaceAll(",", ""),
  );
  expect(isolatedCount).toBeLessThan(fullCount);
  expect(isolatedCount).toBeLessThan(1_000);

  await page.goBack();
  await expect(status).toHaveText(fullState);
  await expect(
    page.getByRole("button", { name: "Isolate connections" }),
  ).toHaveAttribute("aria-pressed", "false");
  expect(page.url()).toBe(fullUrl);

  await page.goForward();
  await expect(
    page.getByRole("button", { name: "Unisolate connections" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(status).not.toHaveText(fullState);

  await page.getByRole("button", { name: "Unisolate connections" }).click();
  await expect(
    page.getByRole("button", { name: "Isolate connections" }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(status).toHaveText(fullState!);
  expect(page.url()).toBe(fullUrl);
});

test("search excludes the unfiltered historical cloud", async ({ page }) => {
  await page.goto(cloudPath);
  const fullState = await fullNodes(page);
  const fullCount = Number(fullState.match(/[\d,]+/)?.[0].replaceAll(",", ""));

  await page.getByLabel("Search the atlas").fill("pretraining");
  await expect(mapStatus(page)).toContainText("match “pretraining”");
  const matchCount = Number(
    (await mapStatus(page).textContent())?.match(/[\d,]+/)?.[0].replaceAll(",", ""),
  );
  expect(matchCount).toBeLessThan(fullCount);
  await expect(page.locator(".graph-header")).toContainText(
    `${matchCount.toLocaleString()} nodes`,
  );

  await page.getByLabel("Search the atlas").fill("");
  await expect(mapStatus(page)).toHaveText(fullState);
});

test("paper lens and arrow-key graph navigation stay concise", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(corePath);
  const filters = page.locator(".filters");
  const showFilters = filters.locator(".mobile-filter-toggle");
  if ((page.viewportSize()?.width ?? 1000) <= 720) {
    await expect(showFilters).toBeVisible();
    await showFilters.tap();
    await expect(showFilters).toHaveAttribute("aria-expanded", "true");
  }
  await expect(filters.getByText("Paper", { exact: true })).toBeVisible();
  await expect(filters).not.toContainText("Paper / context");
  const paperLens = filters.getByRole("button", { name: /Paper\s+[,\d]+/ });
  await paperLens.click();
  await expect(paperLens).toHaveAttribute("aria-pressed", "true");
  await fullNodes(page);

  const graph = page.getByLabel(/Interactive (3D )?research graph/);
  const picker = page.getByLabel("Choose a visible graph node");
  await expect(graph.locator("canvas:not(.cloud-plane)")).toBeVisible();
  await expect(page.getByRole("button", { name: /Reset (3D )?view/ })).toBeVisible();
  await expect(graph).toContainText(/drag (rotates|pans)/);
  let selected: string;
  if ((await picker.evaluate((element) => element.tagName)) === "SELECT") {
    const option = picker.locator("option").filter({ hasText: /Paper · AI4AI-Bench/ });
    await expect(option).toBeAttached({ timeout: 20_000 });
    selected = (await option.getAttribute("value"))!;
    await picker.selectOption(selected);
  } else {
    await picker.fill("AI4AI-Bench");
    await page.getByRole("option", { name: /AI4AI-Bench/ }).click();
    selected = await picker.inputValue();
  }
  await expect(picker).toHaveValue(selected);
  await page.getByRole("button", { name: "Open paper", exact: true }).click();
  const closePaper = page.getByRole("button", { name: "Close paper details" });
  await expect(closePaper).toBeVisible();
  await expect(page.getByRole("heading", { name: "Related work" })).toBeVisible();
  await expect(page.getByText("Competitive landscape", { exact: true })).toHaveCount(0);
  await closePaper.click();
  await expect(picker).toHaveValue(selected);
  await graph.focus();
  await page.keyboard.press("ArrowRight");
  await expect(picker).not.toHaveValue("");
  if ((page.viewportSize()?.width ?? 1_440) <= 1_100) {
    await expect(page.locator("#map-inspector")).toBeFocused();
  } else {
    await expect(graph).toBeFocused();
  }
});

test("daily discovery proves intake coverage and preserves all relevant papers", async ({
  page,
}) => {
  await page.goto(corePath);
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
  const dailyStatus = page
    .getByRole("status")
    .filter({ hasText: /[,\d]+ daily papers available/ });
  await expect(dailyStatus).toBeVisible();
  const available = Number(
    ((await dailyStatus.textContent())?.match(/[\d,]+/)?.[0] ?? "0").replaceAll(
      ",",
      "",
    ),
  );
  await expect(page.getByLabel("Paper result pages")).toContainText(
    `Page 1 of ${Math.ceil(available / 30)}`,
  );
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

  await page.goto(corePath);
  await expect(page.getByRole("alert")).toContainText("Atlas request failed (503)");
  unavailable = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("status")).toContainText("Building the atlas");
  await expect(page.getByText("Atlas", { exact: true })).toBeVisible();
});

test("search views announce empty results and offer working resets", async ({
  page,
}) => {
  await page.goto(corePath);
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
  await page.goto(corePath);
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
  await page.goto(corePath);
  await page.getByRole("button", { name: "Library" }).click();
  await page.getByLabel("Search the atlas").fill("GENERALIZATION MECHANICS");
  await page.getByRole("button", { name: /Open GENERALIZATION MECHANICS/i }).click();

  const dialog = page.getByRole("dialog", { name: /GENERALIZATION MECHANICS/i });
  await expect(dialog.getByLabel("Pinned reading source")).toBeVisible();
  await expect(dialog.getByText("HTML source SHA-256", { exact: true })).toBeVisible();
  await scan(page);
});

test("researched briefs are ranked by one-decimal feasibility", async ({ page }) => {
  await page.goto(corePath);
  await page.getByRole("button", { name: "Briefs" }).click();

  const scoreCards = page.locator(".featured-briefs .card-score");
  await expect(scoreCards.first()).toBeVisible({ timeout: 15_000 });
  const scoreLabels = await scoreCards.allTextContents();
  const scores = scoreLabels.map((label) => Number.parseFloat(label));
  expect(scores.length).toBeGreaterThan(1);
  expect(scores).toEqual([...scores].sort((left, right) => right - left));
  expect(scoreLabels.every((label) => /^\d+\.\d feasibility$/.test(label))).toBe(true);
});

test("cross-scale calibration exposes its complete validation protocol", async ({
  page,
}) => {
  await page.goto(corePath);
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
  await page.goto(corePath);
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
  const techniqueLabel = page.locator(".heatmap .col-label").first();
  await expect(techniqueLabel).toHaveCSS("writing-mode", "horizontal-tb");
  await expect(techniqueLabel).toHaveCSS("transform", "none");

  const ideaLabel = page.locator(".factor-map > span").first();
  await expect(ideaLabel).toHaveCSS("white-space", "normal");
  await expect(ideaLabel).toHaveCSS("text-overflow", "clip");
  expect(
    await page
      .locator(".factor-map > span")
      .evaluateAll((labels) =>
        labels.every((label) => label.scrollWidth <= label.clientWidth + 1),
      ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);

  const point = page.locator(".frontier-point").first();
  const pointLabel = await point.locator("title").textContent();
  const ideaTitle = pointLabel?.replace(/: \d+\.\d feasibility,.*$/, "");
  if (!ideaTitle) throw new Error("Frontier point has no idea title");
  await point.focus();
  await expect(point).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Map", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(
    page.getByRole("heading", { name: ideaTitle, exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "Idea feasibility frontier" }),
  ).toBeVisible();

  const tableToggles = page.getByText("View data table");
  await expect(tableToggles).toHaveCount(11);
  for (const toggle of await tableToggles.all()) await toggle.click();
  await expect(page.getByRole("table")).toHaveCount(11);
  await scan(page);
});

test("coverage reports partial extraction state honestly", async ({ page }) => {
  await page.goto(corePath);
  await page.getByRole("button", { name: "Coverage" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Historical intake stays complete without loading it all at once",
    }),
  ).toBeVisible();

  const accessHeading = page.getByRole("heading", {
    name: "Retrieval routes are classified, not equally complete",
  });
  const partialStatus = page.getByText(/^Partial Text\s+[\d,]+$/);
  if ((await accessHeading.count()) > 0) {
    await expect(accessHeading).toBeVisible();
    if ((await partialStatus.count()) > 0) {
      await expect(partialStatus).toBeVisible();
      await expect(page.getByText(/partial extracts remain visible/i)).toBeVisible();
    } else {
      await expect(
        page.getByText(/no partial extracts remain in the current ledger/i),
      ).toBeVisible();
    }
  } else {
    await expect(partialStatus).toHaveCount(0);
  }
  await expect(page.getByText("historical Papers", { exact: true })).toBeVisible();
  await scan(page);
});
