import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fullNodes, mapStatus } from "./map";

const shard = /\/data\/papers\/[a-f0-9]{64}\.json(?:\?.*)?$/;

async function cloudLinks() {
  const root = join(process.cwd(), "public", "data", "cloud");
  const names = (await readdir(root)).filter((name) =>
    /^\d{4}-\d{2}\.json$/.test(name),
  );
  const links = new Map<string, string>();
  await Promise.all(
    names.map(async (name) => {
      const metadata = JSON.parse(await readFile(join(root, name), "utf8")) as {
        papers: string[][];
      };
      for (const paper of metadata.papers) links.set(paper[1], paper[2]);
    }),
  );
  return links;
}

function trackShard(page: Page): string[] {
  const hits: string[] = [];
  page.on("request", (request) => {
    if (shard.test(request.url())) hits.push(request.url());
  });
  return hits;
}

async function showFilters(page: Page) {
  const toggle = page.locator(".mobile-filter-toggle");
  if (await toggle.isVisible()) await toggle.click();
}

async function loadMap(page: Page, path = "/#?k=tri") {
  await page.goto(path);
  await expect(page.getByLabel(/Interactive (3D )?research graph/)).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByLabel("Choose a visible graph node")).toBeAttached();
}

async function scanAxe(page: Page) {
  const report = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(report.violations).toEqual([]);
}

async function hoverNode(
  page: Page,
  box: { x: number; y: number; width: number; height: number },
  label: string,
  orbit = false,
): Promise<Locator> {
  const tooltip = page.locator(".float-tooltip-kap");
  const offsets = [0, -16, 16, -32, 32, -48, 48];
  const seen = new Set<string>();
  for (let view = 0; view < (orbit ? 3 : 1); view += 1) {
    for (const y of offsets) {
      for (const x of offsets) {
        await page.mouse.move(box.x + box.width / 2 + x, box.y + box.height / 2 + y);
        await page.waitForTimeout(60);
        const text = await tooltip.textContent();
        if (text) seen.add(text);
        if (text?.includes(label)) return tooltip;
      }
    }
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 110, y + 28, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(180);
  }
  throw new Error(
    `Could not hover ${label}; bounds ${JSON.stringify(box)}; saw ${[...seen].join(", ")}`,
  );
}

async function cloudPoint(
  page: Page,
): Promise<{ x: number; y: number; title: string }> {
  const graph = page.getByLabel("Interactive 3D research graph");
  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const tip = page.locator(".cloud-tip");
  const core = page.locator(".swarm-tip:not(.cloud-tip)");
  for (const y of [0.45, 0.55, 0.65, 0.75, 0.35]) {
    for (const x of [0.25, 0.4, 0.55, 0.7, 0.8]) {
      const point = { x: box.x + box.width * x, y: box.y + box.height * y };
      await page.mouse.move(point.x, point.y);
      await page.waitForTimeout(350);
      let label = (await tip.count()) ? await tip.textContent() : null;
      if (label === "Loading Paper…") {
        await page.waitForTimeout(700);
        label = (await tip.count()) ? await tip.textContent() : null;
      }
      if (label?.startsWith("Paper · ") && (await core.count()) === 0) {
        return { ...point, title: label.slice("Paper · ".length) };
      }
    }
  }
  throw new Error("No historical paper point accepted hover input");
}

test("the initial map enables every lens", async ({ page }) => {
  const hits = trackShard(page);
  await loadMap(page, "/");
  await showFilters(page);
  await fullNodes(page);
  await expect(page.getByRole("button", { name: /Paper\s+[,\d]+/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(hits).toHaveLength(1);
});

test("history streams points without eager paper metadata", async ({ page }) => {
  await loadMap(page, "/");
  await showFilters(page);
  await fullNodes(page);
  const resources = await page.evaluate(() =>
    performance.getEntriesByType("resource").map((entry) => entry.name),
  );
  const points = resources.filter((url) =>
    /\/data\/cloud\/\d{4}-\d{2}\.bin(?:\?.*)?$/.test(url),
  );
  const metadata = resources.filter((url) =>
    /\/data\/cloud\/\d{4}-\d{2}\.json(?:\?.*)?$/.test(url),
  );

  expect(points.length).toBeGreaterThan(0);
  expect(metadata).toEqual([]);
});

test("the paper lens fetches its shard once", async ({ page }) => {
  test.setTimeout(90_000);
  const hits = trackShard(page);
  await loadMap(page);
  await showFilters(page);
  const lens = page.getByRole("button", { name: /Paper\s+[,\d]+/ });
  await lens.click();
  await fullNodes(page);
  expect(hits).toHaveLength(1);

  await lens.click();
  await lens.click();
  await fullNodes(page);
  expect(hits).toHaveLength(1);
});

test("search fetches the paper shard once", async ({ page }) => {
  const hits = trackShard(page);
  await loadMap(page);
  await page.getByLabel("Search the atlas").fill("hemispheric redundancy");
  await expect(mapStatus(page)).toContainText(/visible graph nodes? match/);
  await expect(mapStatus(page)).not.toContainText("0 visible");
  expect(hits).toHaveLength(1);
});

test("a bare paper deep link selects it and opens evidence explicitly", async ({
  page,
}) => {
  const hits = trackShard(page);
  await loadMap(page, "/#?s=paper-1");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue(
    /In Two Minds|paper-1/,
  );
  await expect(page.getByRole("heading", { name: "In Two Minds" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Open paper", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("In Two Minds", {
    timeout: 20_000,
  });
  expect(hits).toHaveLength(1);
});

test("hover labels a node and click keeps details in the inspector", async ({
  page,
}, testInfo) => {
  test.skip(["android", "iphone"].includes(testInfo.project.name));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1_440, height: 900 });
  await loadMap(page);
  await showFilters(page);
  const fullState = await fullNodes(page);
  const picker = page.getByLabel("Choose a visible graph node");
  const topic = picker.locator("option").filter({ hasText: "Topic · pretraining" });
  const topicId = await topic.getAttribute("value");
  if (!topicId) throw new Error("Pretraining topic is unavailable");
  await picker.selectOption(topicId);
  await page.getByRole("button", { name: "Isolate connections" }).click();
  await expect(mapStatus(page)).not.toHaveText(fullState!);
  await page.waitForTimeout(2_500);
  await page.getByRole("button", { name: "Center selected" }).click();

  const graph = page.getByLabel(/Interactive (3D )?research graph/);
  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const tooltip = await hoverNode(page, box, "Topic · pretraining", true);
  await expect(tooltip).toContainText("Topic · pretraining");
  await expect(tooltip).toHaveCSS("font-family", /Baskerville/);
  await expect(tooltip).toHaveCSS("font-size", "14px");
  await page.mouse.down();
  await page.mouse.up();
  await expect(page.getByRole("heading", { name: "pretraining" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const inspector = await page.getByLabel("Node inspector").boundingBox();
  if (!inspector) throw new Error("Node inspector has no bounds");
  expect(inspector.x).toBeGreaterThanOrEqual(box.x + box.width - 2);
  expect(inspector.width).toBeGreaterThanOrEqual(280);
  expect(inspector.width).toBeLessThanOrEqual(520);
  await page.mouse.move(box.x + 12, box.y + 12);
  await expect(tooltip).toBeHidden();
});

test("historical paper points open the inline inspector", async ({
  page,
}, testInfo) => {
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Historical point picking is covered in Chromium and WebKit",
  );
  const links = await cloudLinks();
  await page.route(/\/data\/cloud\/\d{4}-\d{2}\.json(?:\?.*)?$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 900));
    await route.continue();
  });
  await page.setViewportSize({ width: 1_440, height: 900 });
  await page.goto("/");
  await expect(page.locator(".filters")).toContainText("historical arXiv records", {
    timeout: 20_000,
  });
  await page.waitForTimeout(2_500);

  const point = await cloudPoint(page);
  const tip = page.locator(".cloud-tip");
  await expect(tip).toHaveCSS("font-family", /Baskerville/);
  await expect(tip).toHaveCSS("font-size", "14px");
  await page.mouse.click(point.x, point.y);
  await page.mouse.move(2, 2);

  const inspector = page.getByLabel("Node inspector");
  await expect(inspector.getByRole("heading", { name: point.title })).toBeVisible();
  await expect(inspector.getByRole("link", { name: "View on arXiv" })).toHaveAttribute(
    "href",
    links.get(point.title) ?? "missing historical paper link",
  );
  await expect(inspector.locator("time")).toHaveAttribute(
    "datetime",
    /^\d{4}-\d{2}-\d{2}/,
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Isolate connections" })).toHaveCount(
    0,
  );

  const picker = page.getByLabel("Choose a visible graph node");
  await picker.fill("pretraining");
  await page.getByRole("option", { name: /Topic\s+pretraining/i }).click();
  await expect(inspector.getByRole("heading", { name: "pretraining" })).toBeVisible();
  await expect(inspector.getByRole("link", { name: "View on arXiv" })).toHaveCount(0);
});

test("2D hover and click use the same inline inspector", async ({ page }, testInfo) => {
  test.skip(["android", "iphone"].includes(testInfo.project.name));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1_440, height: 900 });
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
  await loadMap(page);
  await showFilters(page);
  await page.getByRole("button", { name: /Paper\s+[,\d]+/ }).click();
  const picker = page.getByLabel("Choose a visible graph node");
  const filters = page.locator(".filters");
  await expect(filters).toContainText("historical arXiv records");
  const lensCount = await page.locator(".filters .kind-toggle").evaluateAll((toggles) =>
    toggles.reduce((total, toggle) => {
      if (toggle.getAttribute("aria-pressed") !== "true") return total;
      const count = toggle.textContent?.match(/[\d,]+$/)?.[0] ?? "0";
      return total + Number(count.replaceAll(",", ""));
    }, 0),
  );
  const archiveText = await filters.locator(".aside-copy").textContent();
  const archiveCount = Number(
    archiveText?.match(/batches ([\d,]+) historical/)?.[1].replaceAll(",", ""),
  );
  const fullCount = lensCount - archiveCount;
  const fullState = `${fullCount.toLocaleString()} visible graph nodes available.`;
  await expect(mapStatus(page)).toHaveText(fullState, { timeout: 20_000 });
  expect(archiveCount).toBeGreaterThan(0);
  await expect(page.locator(".graph-header")).toContainText(
    `${fullCount.toLocaleString()} nodes`,
  );
  await picker.fill("In-Context Language Learning");
  await page.getByRole("option", { name: /In-Context Language Learning/ }).click();
  await page.getByRole("button", { name: "Isolate connections" }).click();
  await expect(mapStatus(page)).not.toHaveText(fullState!);
  const isolatedOptions = await picker.locator("option").count();
  const isolatedCount = Number(
    (await mapStatus(page).textContent())?.match(/[\d,]+/)?.[0].replaceAll(",", ""),
  );
  expect(isolatedCount).toBe(isolatedOptions - 1);
  await page.waitForTimeout(2_500);
  await page.getByRole("button", { name: "Center selected" }).click();

  const graph = page.getByLabel("Interactive research graph");
  const box = await graph.boundingBox();
  if (!box) throw new Error("2D research graph has no bounds");
  const tooltip = await hoverNode(page, box, "Paper · In-Context Language Learning");
  await expect(tooltip).toContainText("Paper · In-Context Language Learning");
  await expect(tooltip).toHaveCSS("font-family", /Baskerville/);
  await page.mouse.down();
  await page.mouse.up();
  await expect(
    page.getByRole("heading", { name: "In-Context Language Learning" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Unisolate connections" }).click();
  await expect(mapStatus(page)).toHaveText(fullState);
});

test("copied view links include a camera snapshot", async ({ page, context }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: (value: string) => {
          (window as typeof window & { __atlasCopied?: string }).__atlasCopied = value;
          return Promise.resolve();
        },
      },
    });
  });
  await loadMap(page);
  await showFilters(page);
  await page.getByRole("button", { name: /Paper\s+[,\d]+/ }).click();
  await fullNodes(page);
  const header = page.locator(".graph-header > div");
  await expect(header).toContainText(/[,\d]+ nodes/, { timeout: 20_000 });
  await expect(header).not.toContainText("drawn");
  const picker = page.getByLabel("Choose a visible graph node");
  await picker.fill("Massive Spikes in LLMs are Bias Vectors");
  await page.getByRole("option", { name: /Massive Spikes in LLMs/ }).click();
  await expect(header).toContainText(/[,\d]+ nodes/);
  await page.getByRole("button", { name: "Center selected" }).click();
  await page.getByRole("button", { name: "Copy a link to this atlas view" }).click();
  const copied = await page.evaluate(
    () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
  );
  const camera = new URL(copied).hash
    .match(/c=1_([^&]+)/)?.[1]
    .split("_")
    .map(Number);
  const selectedId = new URLSearchParams(
    new URL(page.url()).hash.replace(/^#\?/, ""),
  ).get("s");
  if (!selectedId) throw new Error("Selected paper is missing from the atlas URL");
  expect(camera).toHaveLength(6);
  expect(camera?.every(Number.isFinite)).toBe(true);
  const shared = await context.newPage();
  await shared.goto(copied);
  await expect(shared.getByLabel("Choose a visible graph node")).toHaveValue(
    /Massive Spikes in LLMs/,
  );
  expect(
    new URLSearchParams(new URL(shared.url()).hash.replace(/^#\?/, "")).get("s"),
  ).toBe(selectedId);
  await expect(shared.getByLabel(/Interactive (3D )?research graph/)).toBeVisible();
  await shared.close();
});

test("a failed paper shard retries once", async ({ page }) => {
  let attempts = 0;
  await page.route("**/data/papers/*.json", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, body: "Unavailable" });
      return;
    }
    await route.continue();
  });

  await loadMap(page);
  await page.getByLabel("Search the atlas").fill("hemispheric redundancy");
  await expect(page.getByRole("alert")).toContainText(
    "Paper index unavailable: Paper asset request failed (503)",
  );
  await page.getByRole("button", { name: "Retry papers" }).click();
  await expect(mapStatus(page)).toContainText(/visible graph nodes? match/);
  await expect(mapStatus(page)).not.toContainText("0 visible");
  expect(attempts).toBe(2);
});

test("URL state hydrates all map controls", async ({ page }) => {
  await loadMap(
    page,
    "/#?q=alignment&s=topic%3Aalignment&k=ti&f=5.5&x=topic%3Aalignment&l=c",
  );
  await showFilters(page);

  await expect(page.getByLabel("Search the atlas")).toHaveValue("alignment");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue(
    "topic:alignment",
  );
  await expect(page.getByLabel("Minimum feasibility")).toHaveValue("5.5");
  await expect(
    page.getByRole("button", { name: "connections", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const filters = page.locator(".filters");
  await expect(filters.getByRole("button", { name: /^Topic\s/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(filters.getByRole("button", { name: /^Trick\s/ })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("history restores pushed views", async ({ page }) => {
  await loadMap(page);
  await page.getByRole("button", { name: "Daily", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Daily", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "Library", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "Collection entry library" }),
  ).toBeVisible();

  await page.goBack();
  await expect(
    page.getByRole("button", { name: "Daily", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.goForward();
  await expect(
    page.getByRole("button", { name: "Library", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});

test("invalid IDs are discarded safely", async ({ page }) => {
  const hits = trackShard(page);
  await loadMap(page, "/#?s=%3Cscript%3E&x=bad%20id&k=tt&f=99");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue("");
  await expect(page.getByLabel("Minimum feasibility")).toHaveValue("1");
  await page.waitForTimeout(250);
  expect(hits).toHaveLength(1);

  await page.goto("/#?s=missing-node");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue("");
  await expect.poll(() => page.url()).not.toContain("s=missing-node");
});

test("clipboard failure is announced", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: () => Promise.reject(new Error("denied")) },
    });
  });
  await loadMap(page);
  const copy = page.getByRole("button", { name: "Copy a link to this atlas view" });
  await copy.click();
  await expect(copy).toContainText("Try again");
  await expect(page.locator(".share-link").getByRole("status")).toContainText(
    "Atlas link could not be copied",
  );
});

test("nearby nodes support keyboard entry", async ({ page }) => {
  await loadMap(page, "/#?s=topic%3Aalignment");
  await fullNodes(page);
  const nearby = page.locator(".nearby").getByRole("button").first();
  const initial = await page.getByLabel("Choose a visible graph node").inputValue();
  await nearby.focus();
  await expect(nearby).toBeFocused();
  await page.keyboard.press("Enter");
  await expect
    .poll(async () => {
      const selected = await page
        .getByLabel("Choose a visible graph node")
        .inputValue();
      return selected !== initial || (await page.getByRole("dialog").count()) > 0;
    })
    .toBe(true);
});

test("the graph has no ambient labels", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
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
  await loadMap(page);
  const tooltip = page.locator(".float-tooltip-kap");
  await expect(tooltip).toBeHidden();

  await page.getByLabel("Search the atlas").fill("alignment");
  await expect(tooltip).toBeHidden();
  await page.getByLabel("Search the atlas").fill("");
  await page.getByRole("button", { name: "connections", exact: true }).click();
  await expect(tooltip).toBeHidden();
});

test("details panel resizes and returns to its default", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loadMap(page);
  const separator = page.getByRole("separator", { name: "Resize details panel" });
  const inspector = page.getByLabel("Node inspector");
  await expect(separator).toBeVisible();
  await expect(separator).toHaveAttribute("aria-valuenow", "330");

  await separator.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(separator).toHaveAttribute("aria-valuenow", "346");
  await expect
    .poll(async () => Math.round((await inspector.boundingBox())?.width ?? 0))
    .toBe(346);

  const box = await separator.boundingBox();
  if (!box) throw new Error("Resize separator has no bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + 180);
  await page.mouse.down();
  await page.mouse.move(box.x - 64, box.y + 180, { steps: 4 });
  await page.mouse.up();
  const stored = Number(await separator.getAttribute("aria-valuenow"));
  expect(stored).toBeGreaterThan(346);
  await page.reload();
  await expect(separator).toHaveAttribute("aria-valuenow", String(stored));
  expect(page.url()).not.toContain("panel");

  await separator.focus();
  await page.keyboard.press("Enter");
  await expect(separator).toHaveAttribute("aria-valuenow", "330");
  await expect
    .poll(async () => Math.round((await inspector.boundingBox())?.width ?? 0))
    .toBe(330);

  await separator.focus();
  await page.keyboard.press("ArrowLeft");
  await page.getByRole("button", { name: "Reset panel width" }).click();
  await expect(separator).toHaveAttribute("aria-valuenow", "330");
});

test("details panel resize control is hidden in stacked layouts", async ({ page }) => {
  await page.setViewportSize({ width: 1_101, height: 844 });
  await loadMap(page);
  const separator = page.getByRole("separator", { name: "Resize details panel" });
  await separator.focus();
  await page.setViewportSize({ width: 1_100, height: 844 });
  await expect(page.getByLabel("Node inspector")).toBeFocused();
  await expect(
    page.getByRole("separator", { name: "Resize details panel", includeHidden: true }),
  ).toBeHidden();

  await page.setViewportSize({ width: 1_101, height: 844 });
  await page.getByRole("button", { name: "Reset panel width" }).focus();
  await page.setViewportSize({ width: 1_100, height: 844 });
  await expect(page.getByLabel("Node inspector")).toBeFocused();
});

test("context loss falls back to 2D", async ({ page }) => {
  await loadMap(page);
  const graph3d = page.getByLabel("Interactive 3D research graph");
  if (await graph3d.count()) {
    await graph3d.locator("canvas").first().dispatchEvent("webglcontextlost");
    await expect(page.getByLabel("Interactive research graph")).toContainText(
      "2D compatibility · semantic",
    );
    await expect(page.locator(".graph-status")).toContainText(
      "3D view paused. You’re in the 2D compatibility view.",
    );
    await page.getByRole("button", { name: "Retry 3D" }).click();
    const rebuilt = page.getByLabel("Interactive 3D research graph");
    await expect(rebuilt.locator("canvas")).toBeVisible();
    await rebuilt.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByLabel("Choose a visible graph node")).not.toHaveValue("");
    await expect(page.getByRole("button", { name: "Close inspector" })).toBeVisible();
  } else {
    await expect(page.getByLabel("Interactive research graph")).toContainText(
      "2D compatibility · semantic",
    );
  }
});

test("320px map passes axe", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await loadMap(page);
  await scanAxe(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
});

test("200% map passes axe", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await loadMap(page);
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await scanAxe(page);
});
