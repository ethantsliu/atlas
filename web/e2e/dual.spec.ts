import { expect, test } from "@playwright/test";

test("the map exposes one 3D view and preserves selection", async ({ page }) => {
  await page.goto("/#?k=tri&s=topic%3Aalignment");

  await expect(page.getByRole("group", { name: "map dimension" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "2D", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();

  const result = page
    .getByLabel("Interactive 3D research graph", { exact: true })
    .or(page.locator(".graph-status"));
  await expect(result).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();
});
