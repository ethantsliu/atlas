import { expect, type Page } from "@playwright/test";

export function mapStatus(page: Page) {
  return page
    .locator(".map-layout > p.sr-only[role=status]")
    .filter({ hasText: /visible graph nodes/ });
}

export async function fullNodes(page: Page): Promise<string> {
  const filters = page.locator(".filters");
  const paperLens = filters.locator(".kind-toggle").nth(2);
  const paperOn = (await paperLens.getAttribute("aria-pressed")) === "true";
  let archiveCount = 0;
  if (paperOn) {
    await expect(filters).toContainText("historical arXiv papers", {
      timeout: 20_000,
    });
    const copy = await filters.locator(".aside-copy").textContent();
    archiveCount = Number((copy?.match(/[\d,]+/)?.[0] ?? "0").replaceAll(",", ""));
  }
  const cloudVisible =
    (await page.getByLabel("Interactive 3D research graph").count()) > 0 ||
    (await page.locator(".cloud-plane[data-engine]").count()) > 0;
  const toggles = filters.locator(".kind-toggle");
  const counts = await Promise.all(
    [0, 1, 2, 3].map(async (index) => {
      const toggle = toggles.nth(index);
      if ((await toggle.getAttribute("aria-pressed")) !== "true") return 0;
      const text = await toggle.textContent();
      const count = Number((text?.match(/[\d,]+$/)?.[0] ?? "0").replaceAll(",", ""));
      return index === 2 && !cloudVisible ? count - archiveCount : count;
    }),
  );
  const total = counts.reduce((sum, count) => sum + count, 0);

  const expected = `${total.toLocaleString()} visible graph nodes available.`;
  await expect(mapStatus(page)).toHaveText(expected, { timeout: 20_000 });
  return expected;
}
