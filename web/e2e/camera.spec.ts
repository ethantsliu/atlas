import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const view = "1_120_-40_75_40_25_-15";

async function mockCopy(context: BrowserContext) {
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
}

async function copyCamera(page: Page) {
  await page.getByRole("button", { name: "Copy a link to this atlas view" }).click();
  const copied = await page.evaluate(
    () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
  );
  return new URLSearchParams(new URL(copied).hash.replace(/^#\?/, "")).get("c");
}

async function steadyCamera(page: Page) {
  let prior: string | null = null;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await page.waitForTimeout(300);
    const current = await copyCamera(page);
    if (current && current === prior) return current;
    prior = current;
  }
  return prior;
}

function cameraParts(value: string | null) {
  return value?.split("_").slice(1).map(Number) ?? [];
}

test("camera links restore once and leave navigation in control", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "3D camera restoration is covered in Chromium and WebKit",
  );
  await mockCopy(context);
  await page.goto(`/#?k=tri&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => copyCamera(page), { timeout: 20_000 }).toBe(view);
  await page.waitForTimeout(1_000);
  expect(await copyCamera(page)).toBe(view);
  await page.locator(".graph-node-picker select").selectOption("topic:alignment");
  await page.waitForTimeout(1_000);
  expect(await copyCamera(page)).toBe(view);

  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -1_200);
  await expect.poll(() => copyCamera(page)).not.toBe(view);
  const moved = await copyCamera(page);
  expect(moved).not.toBe(view);

  await page.waitForTimeout(1_500);
  expect(await copyCamera(page)).toBe(moved);
});

test("camera links restore without ForceGraph core nodes", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "3D camera restoration is covered in Chromium and WebKit",
  );
  await mockCopy(context);
  await page.goto(`/#?k=p&c=${view}`);
  await expect(page.getByLabel("Interactive 3D research graph")).toBeVisible({
    timeout: 20_000,
  });
  await expect.poll(() => copyCamera(page), { timeout: 20_000 }).toBe(view);
});

test("navigation cancels a deferred camera restore", async ({
  context,
  page,
}, testInfo) => {
  test.setTimeout(60_000);
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Deferred camera navigation is covered in Chromium and WebKit",
  );
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(/\/data\/cloud\/index\.json(?:\?.*)?$/, async (route) => {
    await gate;
    await route.continue();
  });
  await mockCopy(context);
  await page.goto(`/#?k=trpi&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  const initial = await copyCamera(page);
  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 100, y + 35, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => copyCamera(page)).not.toBe(initial);
  const moved = await steadyCamera(page);

  release();
  await expect(page.locator(".filters")).toContainText("historical arXiv records", {
    timeout: 20_000,
  });
  const after = await steadyCamera(page);
  const movedParts = cameraParts(moved);
  const afterParts = cameraParts(after);
  expect(afterParts.slice(0, 4)).toEqual(movedParts.slice(0, 4));
  expect(Math.abs(afterParts[4] - movedParts[4])).toBeLessThanOrEqual(2);
  expect(Math.abs(afterParts[5] - movedParts[5])).toBeLessThanOrEqual(2);
  expect(after).not.toBe(view);
  expect(moved).not.toBe(view);
});
