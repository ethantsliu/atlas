import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { archivePapers } from "./map";

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

async function readCameraQuiet(page: Page) {
  await page
    .getByRole("button", { name: "Copy a link to this atlas view" })
    .evaluate((button) => (button as HTMLButtonElement).click());
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

async function chooseAlignment(page: Page) {
  const picker = page.getByLabel("Choose a visible graph node");
  if ((await picker.evaluate((element) => element.tagName)) === "SELECT") {
    await picker.selectOption("topic:alignment");
    return;
  }
  await picker.fill("alignment");
  await page.getByRole("option", { name: /Topic\s+alignment/i }).click();
}

function cameraParts(value: string | null) {
  return value?.split("_").slice(1).map(Number) ?? [];
}

type CameraSnapshot = {
  target: [number, number, number];
  radius: number;
  yaw: number;
  pitch: number;
};

function cameraSnapshot(value: string | null): CameraSnapshot {
  const parts = cameraParts(value);
  if (parts.length !== 6 || !parts.every(Number.isFinite)) {
    throw new Error(`Invalid camera snapshot: ${value}`);
  }
  return {
    target: [parts[0], parts[1], parts[2]],
    radius: parts[3],
    yaw: parts[4],
    pitch: parts[5],
  };
}

async function waitForOrbit(
  page: Page,
  initial: CameraSnapshot,
  degrees = 8,
): Promise<CameraSnapshot | null> {
  const canvas = page
    .getByLabel("Interactive 3D research graph", { exact: true })
    .locator("canvas")
    .first();
  await expect(canvas).toHaveAttribute("data-auto-rotate", "true", {
    timeout: 15_000,
  });
  await page.waitForTimeout(2_000);
  const current = cameraSnapshot(await readCameraQuiet(page));
  return Math.abs(current.yaw - initial.yaw) > degrees &&
    current.pitch !== initial.pitch
    ? current
    : null;
}

function targetDelta(from: CameraSnapshot, to: CameraSnapshot) {
  return to.target.map((value, index) => value - from.target[index]) as [
    number,
    number,
    number,
  ];
}

function length(vector: readonly number[]) {
  return Math.hypot(...vector);
}

function expectOrbitPreserved(before: CameraSnapshot, after: CameraSnapshot) {
  expect(after.radius).toBeCloseTo(before.radius, 1);
  expect(Math.abs(after.yaw - before.yaw)).toBeLessThanOrEqual(1);
  expect(Math.abs(after.pitch - before.pitch)).toBeLessThanOrEqual(1);
}

async function wheelOnGraph(
  page: Page,
  deltaY: number,
  count = 1,
  at: { x: number; y: number } = { x: 0.5, y: 0.5 },
) {
  const graph = page.getByLabel("Interactive 3D research graph");
  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  await page.mouse.move(box.x + box.width * at.x, box.y + box.height * at.y);
  for (let step = 0; step < count; step += 1) {
    await page.mouse.wheel(0, deltaY);
  }
}

test("3D defaults on and a plain focused click keeps idle rotation", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chrome", "Chromium covers idle focus");
  await page.goto("/#?k=tri");
  const graph = page.getByLabel("Interactive 3D research graph", { exact: true });
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect(
    page
      .getByRole("group", { name: "map dimension" })
      .getByRole("button", { name: "3D", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".auto-rotate-status")).toContainText(
    /Auto-rotate in [1-5]s|Auto-rotating/,
  );

  const canvas = graph.locator("canvas").first();
  await expect(canvas).toHaveAttribute("data-auto-rotate", "true", {
    timeout: 15_000,
  });
  const box = await canvas.boundingBox();
  if (!box) throw new Error("3D canvas has no bounds");
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await graph.focus();
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.4);
  await expect(canvas).toHaveAttribute("data-auto-rotate", "true", {
    timeout: 1_000,
  });
});

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
  await chooseAlignment(page);
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
  await page.emulateMedia({ reducedMotion: "reduce" });
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
  await archivePapers(page);
  const after = await steadyCamera(page);
  const movedParts = cameraParts(moved);
  const afterParts = cameraParts(after);
  expect(afterParts.slice(0, 4)).toEqual(movedParts.slice(0, 4));
  expect(after).not.toBe(view);
  expect(moved).not.toBe(view);
});

test("wheel zoom follows the cursor and rotation keeps its new center", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Desktop orbit zoom is covered in Chromium and WebKit",
  );
  await mockCopy(context);
  await page.goto(`/#?k=tri&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => copyCamera(page), { timeout: 20_000 }).toBe(view);
  const initial = cameraSnapshot(view);

  await wheelOnGraph(page, -120, 6, { x: 0.78, y: 0.3 });
  const zoomedValue = await steadyCamera(page);
  const zoomed = cameraSnapshot(zoomedValue);
  expect(length(targetDelta(initial, zoomed))).toBeGreaterThan(0.35);
  expect(zoomed.radius).toBeLessThan(initial.radius);
  expect(zoomed.yaw).toBeCloseTo(initial.yaw, 0);
  expect(zoomed.pitch).toBeCloseTo(initial.pitch, 0);

  await page.waitForTimeout(1_500);
  expect(await copyCamera(page)).toBe(zoomedValue);

  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 90, y + 35, { steps: 8 });
  await page.mouse.up();
  const orbited = cameraSnapshot(await steadyCamera(page));
  expect(length(targetDelta(zoomed, orbited))).toBeLessThan(0.35);
  expect(orbited.radius).toBeCloseTo(zoomed.radius, 1);
  expect(
    Math.abs(orbited.yaw - zoomed.yaw) + Math.abs(orbited.pitch - zoomed.pitch),
  ).toBeGreaterThan(2);

  await wheelOnGraph(page, 120, 6, { x: 0.22, y: 0.72 });
  const restoredValue = await steadyCamera(page);
  const restored = cameraSnapshot(restoredValue);
  expect(length(targetDelta(orbited, restored))).toBeGreaterThan(0.35);
  expect(restored.radius).toBeGreaterThan(orbited.radius);
  expect(Math.abs(restored.yaw - orbited.yaw)).toBeLessThanOrEqual(1);
  expect(Math.abs(restored.pitch - orbited.pitch)).toBeLessThanOrEqual(1);
  await page.waitForTimeout(1_500);
  expect(await copyCamera(page)).toBe(restoredValue);
});

test("idle orbit yields to input and resumes around the same target", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chrome",
    "Chromium covers the native OrbitControls idle lifecycle",
  );
  test.setTimeout(60_000);
  await mockCopy(context);
  await page.setViewportSize({ width: 1_440, height: 900 });
  await page.goto(`/#?k=tri&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => readCameraQuiet(page), { timeout: 20_000 }).toBe(view);
  const initial = cameraSnapshot(view);

  const rotating = await waitForOrbit(page, initial);
  expect(rotating).not.toBeNull();
  if (!rotating) throw new Error("Idle orbit did not start");
  expect(length(targetDelta(initial, rotating))).toBeLessThan(0.35);
  expect(rotating.radius).toBeCloseTo(initial.radius, 1);
  expect(rotating.pitch).not.toBe(initial.pitch);

  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(800);
  const held = cameraSnapshot(await readCameraQuiet(page));
  await page.waitForTimeout(800);
  const stillHeld = cameraSnapshot(await readCameraQuiet(page));
  expectOrbitPreserved(held, stillHeld);
  expect(Math.abs(stillHeld.yaw - held.yaw)).toBeLessThanOrEqual(1);
  expect(length(targetDelta(held, stillHeld))).toBeLessThan(0.35);

  await page.mouse.up();
  await page.waitForTimeout(1_500);
  const released = cameraSnapshot(await readCameraQuiet(page));
  expectOrbitPreserved(stillHeld, released);
  expect(Math.abs(released.yaw - stillHeld.yaw)).toBeLessThanOrEqual(1);

  expect(await waitForOrbit(page, released)).not.toBeNull();

  const beforeWheel = cameraSnapshot(await readCameraQuiet(page));
  await wheelOnGraph(page, -120, 2, { x: 0.7, y: 0.35 });
  await page.waitForTimeout(800);
  const afterWheel = cameraSnapshot(await readCameraQuiet(page));
  expect(afterWheel.radius).toBeLessThan(beforeWheel.radius);
  await page.waitForTimeout(1_200);
  const wheelIdle = cameraSnapshot(await readCameraQuiet(page));
  expectOrbitPreserved(afterWheel, wheelIdle);
});

test("keyboard Center selected interrupts and later resumes idle orbit", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chrome",
    "Chromium covers keyboard interruption of OrbitControls",
  );
  test.setTimeout(60_000);
  await mockCopy(context);
  await page.setViewportSize({ width: 1_440, height: 900 });
  await page.goto(`/#?k=tri&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => readCameraQuiet(page), { timeout: 20_000 }).toBe(view);
  await chooseAlignment(page);
  const center = page.getByRole("button", { name: "Center selected" });
  await expect(center).toBeVisible();

  const waiting = cameraSnapshot(await readCameraQuiet(page));
  expect(await waitForOrbit(page, waiting)).not.toBeNull();

  await center.focus();
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1_000);
  const centered = cameraSnapshot(await readCameraQuiet(page));
  await page.waitForTimeout(1_200);
  const held = cameraSnapshot(await readCameraQuiet(page));
  expectOrbitPreserved(centered, held);

  expect(await waitForOrbit(page, held, 1)).not.toBeNull();
});

test("WebKit keeps cursor-aware fractional trackpad and pinch zoom native", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "safari",
    "Trackpad regression is WebKit-specific",
  );
  await mockCopy(context);
  await page.goto(`/#?k=tri&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => copyCamera(page), { timeout: 20_000 }).toBe(view);
  const initial = cameraSnapshot(view);
  const canvas = graph.locator("canvas:not(.cloud-plane)");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("Research canvas has no bounds");
  await page.mouse.move(box.x + box.width * 0.72, box.y + box.height * 0.28);

  for (let step = 0; step < 8; step += 1) {
    await page.mouse.wheel(0, -7.5);
  }
  const trackedValue = await steadyCamera(page);
  const tracked = cameraSnapshot(trackedValue);
  expect(length(targetDelta(initial, tracked))).toBeGreaterThan(0.35);
  expect(tracked.radius).toBeLessThan(initial.radius);
  expect(tracked.yaw).toBeCloseTo(initial.yaw, 0);
  expect(tracked.pitch).toBeCloseTo(initial.pitch, 0);

  await canvas.dispatchEvent("wheel", {
    deltaY: -120,
    deltaMode: 0,
    ctrlKey: true,
    clientX: box.x + box.width * 0.72,
    clientY: box.y + box.height * 0.28,
  });
  const pinched = cameraSnapshot(await steadyCamera(page));
  expect(length(targetDelta(tracked, pinched))).toBeGreaterThan(0.35);
  expect(pinched.yaw).toBeCloseTo(tracked.yaw, 0);
  expect(pinched.pitch).toBeCloseTo(tracked.pitch, 0);
  expect(Math.abs(pinched.radius - tracked.radius)).toBeGreaterThan(0.5);
});
