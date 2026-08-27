import { expect, test } from "@playwright/test";

test("dimension history preserves the foreground selection", async ({ page }) => {
  await page.goto("/#?d=2&k=tri&s=topic%3Aalignment");
  const map = page.getByRole("group", { name: "map dimension" });
  const twoD = map.getByRole("button", { name: "2D" });
  const threeD = map.getByRole("button", { name: "3D" });

  await expect(twoD).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();

  await threeD.click();
  await expect(page).toHaveURL(/(?:\?|&)d=3(?:&|$)/);
  await expect(threeD).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/(?:\?|&)d=2(?:&|$)/);
  await expect(twoD).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();
});
