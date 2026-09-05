import { expect, test } from "@playwright/test";

test("dimension history preserves the foreground selection", async ({ page }) => {
  await page.goto("/#?d=2&k=tri&s=topic%3Aalignment");
  const map = page.getByRole("group", { name: "map dimension" });
  const twoD = map.getByRole("button", { name: "2D" });
  const threeD = map.getByRole("button", { name: "3D" });

  await expect(twoD).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();

  await threeD.click();
  await expect(threeD).toHaveAttribute("aria-pressed", "true");
  expect(
    new URLSearchParams(new URL(page.url()).hash.replace(/^#\?/, "")).get("d"),
  ).toBeNull();
  const result = page.getByLabel("Interactive 3D research graph", { exact: true }).or(
    page.locator(".graph-status").filter({
      hasText: "3D unavailable; using the 2D fallback.",
    }),
  );
  await expect(result).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/(?:\?|&)d=2(?:&|$)/);
  await expect(twoD).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "alignment" })).toBeVisible();
});
