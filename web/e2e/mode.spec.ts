import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("3D is the only exposed map dimension", async ({ page }) => {
  await page.goto("/#?k=tri");
  const graph = page
    .getByLabel("Interactive 3D research graph", { exact: true })
    .or(page.getByLabel("Interactive research graph", { exact: true }));
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("group", { name: "map dimension" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "2D", exact: true })).toHaveCount(0);
  await expect(page.locator(".graph-header")).toContainText(
    /(?:3D|Compatibility) · semantic frame/,
  );
});

test("the 3D-only toolbar remains accessible at 320px", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chrome", "One Chromium pass covers axe");
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/#?k=tri");
  await expect(
    page.getByLabel("Interactive 3D research graph", { exact: true }),
  ).toBeVisible({ timeout: 20_000 });
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

test("unsupported WebGL uses an automatic compatibility view", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chrome", "Chromium covers capability fallback");
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
  await expect(page.locator(".graph-status")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("group", { name: "map dimension" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "2D", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Interactive research graph")).toBeVisible();
});
