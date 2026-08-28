import { expect, type Page } from "@playwright/test";

export async function has3d(page: Page): Promise<boolean> {
  const graph = page.getByLabel("Interactive 3D research graph", { exact: true });
  const fallback = page.locator(".graph-status").filter({
    hasText: "3D unavailable; using the 2D fallback.",
  });
  await expect
    .poll(async () => (await graph.count()) > 0 || (await fallback.count()) > 0, {
      timeout: 20_000,
    })
    .toBe(true);
  return (await graph.count()) > 0;
}
