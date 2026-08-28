import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

const desktop = new Set(["chrome", "safari"]);
const touch = new Set(["android", "iphone"]);

function dimension(page: Page, label: "2D" | "3D") {
  return page
    .getByRole("group", { name: "map dimension" })
    .getByRole("button", { name: label, exact: true });
}

function heading(page: Page) {
  return page
    .locator("#map-inspector")
    .getByRole("heading", { name: "pretraining", exact: true });
}

async function overview(page: Page, layout = "semantic") {
  const graph = page.getByLabel("Interactive research graph", { exact: true });
  await expect(graph).toContainText(`2D overview · ${layout}`, { timeout: 20_000 });
  await expect(graph.locator("canvas")).toBeVisible();
  await expect(dimension(page, "2D")).toHaveAttribute("aria-pressed", "true");
  return graph;
}

async function selectTopic(page: Page) {
  const label = "Choose a visible graph node";
  const input = page.getByRole("combobox", { name: label }).and(page.locator("input"));
  await expect(input).toHaveAttribute("placeholder", "Find a paper or node…", {
    timeout: 20_000,
  });
  await input.fill("pretraining");
  await page.getByRole("option", { name: /Topic\s+pretraining/i }).click();
  await expect(heading(page)).toBeVisible();
}

async function completeCloud(page: Page) {
  const filters = page.locator(".filters");
  await expect(filters).toContainText("historical arXiv papers", {
    timeout: 30_000,
  });
  const toggles = filters.locator(".kind-toggle");
  const counts = await Promise.all(
    [0, 1, 2, 3].map(async (index) => {
      const toggle = toggles.nth(index);
      if ((await toggle.getAttribute("aria-pressed")) !== "true") return 0;
      const text = await toggle.textContent();
      return Number((text?.match(/[\d,]+$/)?.[0] ?? "0").replaceAll(",", ""));
    }),
  );
  const expected = `${counts
    .reduce((sum, count) => sum + count, 0)
    .toLocaleString()} visible graph nodes available.`;
  await expect(
    page
      .locator(".map-layout > p.sr-only[role=status]")
      .filter({ hasText: /visible graph nodes/ }),
  ).toHaveText(expected, { timeout: 30_000 });
}

async function touchPoint(canvas: Locator) {
  return canvas.evaluate(async (element: HTMLCanvasElement) => {
    await new Promise<void>((done) => requestAnimationFrame(() => done()));
    await new Promise<void>((done) => requestAnimationFrame(() => done()));
    const context = element.getContext("2d");
    if (!context) return null;
    const rect = element.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const limit = Math.min(96, rect.width / 2 - 2, rect.height / 2 - 2);
    for (let x = 0; x <= limit; x += 4) {
      for (const sign of x === 0 ? [1] : [-1, 1]) {
        for (let y = 0; y <= limit; y += 4) {
          const clientX = centerX + x * sign;
          const clientY = centerY + y;
          if (document.elementFromPoint(clientX, clientY) !== element) continue;
          const pixelX = Math.floor(
            ((clientX - rect.left) / rect.width) * element.width,
          );
          const pixelY = Math.floor(
            ((clientY - rect.top) / rect.height) * element.height,
          );
          const pixel = Array.from(context.getImageData(pixelX, pixelY, 1, 1).data);
          if (pixel.every((value, index) => value === [118, 91, 145, 255][index])) {
            return { x: clientX, y: clientY };
          }
        }
      }
    }
    return null;
  });
}

test("3D code and cloud stay lazy until opt-in while foreground state survives", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  test.skip(!desktop.has(testInfo.project.name), "Desktop engines cover 3D opt-in");
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto("/");
  await overview(page);
  await selectTopic(page);
  const trick = page.getByRole("button", { name: /^Trick\s+[\d,]+$/ });
  await trick.click();
  await expect(trick).toHaveAttribute("aria-pressed", "false");

  expect(requests.some((url) => /\/data\/cloud\//.test(url))).toBe(false);
  expect(
    requests.some((url) =>
      /(?:\/src\/components\/map\/Space\.tsx|\/assets\/Space-[\w-]+\.js)/.test(url),
    ),
  ).toBe(false);

  await dimension(page, "3D").click();
  await expect(
    page.getByLabel("Interactive 3D research graph", { exact: true }),
  ).toBeVisible({
    timeout: 20_000,
  });
  await expect
    .poll(() => requests.some((url) => /\/data\/cloud\/index\.json/.test(url)))
    .toBe(true);
  await expect
    .poll(() =>
      requests.some((url) =>
        /(?:\/src\/components\/map\/Space\.tsx|\/assets\/Space-[\w-]+\.js)/.test(url),
      ),
    )
    .toBe(true);
  await completeCloud(page);
  await expect(heading(page)).toBeVisible();
  await expect(trick).toHaveAttribute("aria-pressed", "false");

  for (let entry = 0; entry < 1; entry += 1) {
    await dimension(page, "2D").click();
    await overview(page);
    await dimension(page, "3D").click();
    await expect(
      page.getByLabel("Interactive 3D research graph", { exact: true }),
    ).toBeVisible({ timeout: 20_000 });
    await completeCloud(page);
  }
  expect(requests.filter((url) => /\/data\/cloud\/index\.json/.test(url))).toHaveLength(
    1,
  );
  expect(
    requests.filter((url) =>
      /(?:\/src\/components\/map\/Space\.tsx|\/assets\/Space-[\w-]+\.js)/.test(url),
    ),
  ).toHaveLength(1);
  await dimension(page, "2D").click();
  await overview(page);
  await expect(heading(page)).toBeVisible();
  await expect(trick).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "connections", exact: true }).click();

  await dimension(page, "3D").click();
  await expect(
    page.getByLabel("Interactive 3D research graph", { exact: true }),
  ).toBeVisible({
    timeout: 20_000,
  });
  await expect(heading(page)).toBeVisible();
  await expect(trick).toHaveAttribute("aria-pressed", "false");
  await expect(
    page.getByRole("button", { name: "connections", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("explicit 2D supports a centered touch selection", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  test.skip(!touch.has(testInfo.project.name), "Touch projects cover canvas selection");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/#?d=2&k=t&s=topic%3Apre-training&x=topic%3Apre-training");
  const graph = await overview(page);
  await expect(heading(page)).toBeVisible();
  await page.getByRole("button", { name: "Center selected" }).click();
  await page.getByRole("button", { name: "Close inspector" }).click();
  await expect(heading(page)).toHaveCount(0);

  const canvas = graph.locator("canvas");
  let point: { x: number; y: number } | null = null;
  await expect
    .poll(
      async () => {
        point = await touchPoint(canvas);
        return point;
      },
      { timeout: 20_000 },
    )
    .not.toBeNull();
  if (!point) throw new Error("Centered node has no visible touch target");
  await page.touchscreen.tap(point.x, point.y);
  await expect(heading(page)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("320px 2D default has no overflow or axe violations", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chrome", "One Chromium pass covers 320px axe");
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/");
  await overview(page);
  await page.evaluate(() => document.fonts.ready);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    ),
  ).toBe(false);
  const report = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(report.violations).toEqual([]);
});

test("3D fallback shares the requested dimension", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chrome", "Chromium covers fallback sharing");
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type === "webgl2") return null;
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
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

  await page.goto("/#?d=3&k=tri");
  await expect(page.locator(".graph-status")).toContainText(
    "3D unavailable; using the 2D fallback.",
  );
  await page.getByRole("button", { name: "Copy a link to this atlas view" }).click();
  const copied = await page.evaluate(
    () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
  );
  const params = new URL(copied).hash.replace(/^#\?/, "");

  expect(new URLSearchParams(params).get("d")).toBe("3");
  expect(new URLSearchParams(params).get("c")).not.toBeNull();
  expect(new URL(page.url()).hash).toContain("d=3");
});
