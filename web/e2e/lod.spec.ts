import { expect, test, type Page } from "@playwright/test";

type TraceHost = Window & {
  lodCount?: number;
  lodTrace?: number[];
};

function drawCount(page: Page): Promise<number> {
  return page.evaluate(() => (window as TraceHost).lodCount ?? 0);
}

async function startTrace(page: Page): Promise<void> {
  await page.evaluate(() => {
    const host = window as TraceHost;
    host.lodTrace = host.lodCount ? [host.lodCount] : [];
  });
}

async function stopTrace(page: Page): Promise<number[]> {
  return page.evaluate(() => (window as TraceHost).lodTrace ?? []);
}

test("3D cloud keeps a stable rotation level", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chrome", "Chromium traces WebGL draw levels");
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1_440, height: 900 });
  await page.addInitScript(() => {
    const host = window as TraceHost;
    const wrap = (prototype: WebGLRenderingContext | WebGL2RenderingContext) => {
      const original = prototype.drawArrays;
      prototype.drawArrays = function (mode, first, count) {
        if (mode === this.POINTS && count >= 50_000) {
          host.lodCount = count;
          if (host.lodTrace && host.lodTrace.at(-1) !== count) {
            host.lodTrace.push(count);
          }
        }
        return original.call(this, mode, first, count);
      };
    };
    wrap(WebGLRenderingContext.prototype);
    wrap(WebGL2RenderingContext.prototype);
  });
  await page.goto("/#?d=3&k=trpi");
  const graph = page.getByLabel("Interactive 3D research graph", { exact: true });
  await expect(graph).toBeVisible({ timeout: 20_000 });
  const paperToggle = page.locator(".filters .kind-toggle").nth(2);
  await expect
    .poll(() => paperToggle.getAttribute("data-archive-count"), { timeout: 30_000 })
    .not.toBeNull();

  const expected = Number((await paperToggle.getAttribute("data-archive-count")) ?? 0);
  expect(expected).toBeGreaterThan(100_000);
  await expect.poll(() => drawCount(page), { timeout: 60_000 }).toBe(expected);
  const full = await drawCount(page);
  await startTrace(page);

  const canvas = graph.locator("canvas").first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("3D canvas has no bounds");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  // One real drag update is sufficient to exercise OrbitControls. Twelve
  // interpolated updates force twelve full 3.15M-point software-GPU renders in
  // CI and can consume the entire test timeout without changing the invariant.
  await page.mouse.move(x + 120, y + 60);
  await expect.poll(() => drawCount(page), { timeout: 10_000 }).toBe(full);
  await page.mouse.up();
  await expect.poll(() => drawCount(page), { timeout: 10_000 }).toBe(full);
  await page.waitForTimeout(1_000);
  expect(await drawCount(page)).toBe(full);
  expect(await stopTrace(page)).toEqual([full]);

  // Hardware renderers continue rotating; software renderers intentionally
  // remain still when a full 3.15M-point frame misses the smooth-frame budget.
  await page.waitForTimeout(4_000);
  expect(await drawCount(page)).toBe(full);
  expect(await stopTrace(page)).toEqual([full]);

  await expect(
    page.getByRole("group", { name: "historical paper dot density" }),
  ).toHaveCount(0);
});
