import { expect, test, type Page } from "@playwright/test";

const engines = new Set(["chrome", "safari", "iphone"]);

async function loadGraph(page: Page, project: string) {
  await page.goto("/#?d=2&k=tri&s=topic%3Apre-training");
  if (project !== "iphone") {
    await page
      .getByRole("group", { name: "map dimension" })
      .getByRole("button", { name: "3D", exact: true })
      .click();
  }
  const label =
    project === "iphone"
      ? "Interactive research graph"
      : "Interactive 3D research graph";
  return page.getByLabel(label, { exact: true });
}

test("keyboard close restores graph focus", async ({ page }, testInfo) => {
  test.skip(
    !engines.has(testInfo.project.name),
    "Focus coverage uses both engines and touch",
  );
  const graph = await loadGraph(page, testInfo.project.name);
  const close = page.getByRole("button", { name: "Close inspector" });
  await expect(graph).toBeVisible();
  await expect(close).toBeVisible();

  await close.focus();
  await page.keyboard.press("Enter");

  await expect(close).toHaveCount(0);
  await expect(graph).toBeFocused();
});

test("pointer close does not steal graph focus", async ({ page }, testInfo) => {
  test.skip(
    !engines.has(testInfo.project.name),
    "Focus coverage uses both engines and touch",
  );
  const graph = await loadGraph(page, testInfo.project.name);
  const close = page.getByRole("button", { name: "Close inspector" });
  await expect(graph).toBeVisible();
  await expect(close).toBeVisible();

  if (testInfo.project.name === "iphone") await close.tap();
  else await close.click();

  await expect(close).toHaveCount(0);
  await expect(graph).not.toBeFocused();
});
