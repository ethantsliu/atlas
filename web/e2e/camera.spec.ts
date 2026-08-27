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

function sightline(view: CameraSnapshot): [number, number, number] {
  const yaw = (view.yaw * Math.PI) / 180;
  const pitch = (view.pitch * Math.PI) / 180;
  return [
    -Math.sin(yaw) * Math.cos(pitch),
    -Math.sin(pitch),
    -Math.cos(yaw) * Math.cos(pitch),
  ];
}

function dot(left: readonly number[], right: readonly number[]) {
  return left.reduce((total, value, index) => total + value * right[index], 0);
}

function expectOrbitPreserved(before: CameraSnapshot, after: CameraSnapshot) {
  expect(after.radius).toBeCloseTo(before.radius, 1);
  expect(Math.abs(after.yaw - before.yaw)).toBeLessThanOrEqual(1);
  expect(Math.abs(after.pitch - before.pitch)).toBeLessThanOrEqual(1);
}

function expectForwardFlight(
  before: CameraSnapshot,
  after: CameraSnapshot,
  minimum = 0,
) {
  const delta = targetDelta(before, after);
  const distance = length(delta);
  const progress = dot(delta, sightline(before));
  const sideways = Math.sqrt(Math.max(0, distance ** 2 - progress ** 2));
  expect(progress).toBeGreaterThan(minimum);
  expect(sideways).toBeLessThan(0.35);
  expectOrbitPreserved(before, after);
}

async function wheelOnGraph(page: Page, deltaY: number, count = 1) {
  const graph = page.getByLabel("Interactive 3D research graph");
  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let step = 0; step < count; step += 1) {
    await page.mouse.wheel(0, deltaY);
  }
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

test("repeated wheel input flies through the target without losing orbit control", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Desktop fly-through is covered in Chromium and WebKit",
  );
  await mockCopy(context);
  await page.goto(`/#?k=tri&c=${view}`);
  const graph = page.getByLabel("Interactive 3D research graph");
  await expect(graph).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => copyCamera(page), { timeout: 20_000 }).toBe(view);
  const initial = cameraSnapshot(view);

  await wheelOnGraph(page, -120, 6);
  const crossedValue = await steadyCamera(page);
  const crossed = cameraSnapshot(crossedValue);
  const originalCameraDistance = initial.radius / Math.tan((25 * Math.PI) / 180);
  expectForwardFlight(initial, crossed, originalCameraDistance);

  await page.waitForTimeout(1_500);
  expect(await copyCamera(page)).toBe(crossedValue);

  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 90, y + 35, { steps: 8 });
  await page.mouse.up();
  const orbited = cameraSnapshot(await steadyCamera(page));
  expect(length(targetDelta(crossed, orbited))).toBeLessThan(0.35);
  expect(orbited.radius).toBeCloseTo(crossed.radius, 1);
  expect(
    Math.abs(orbited.yaw - crossed.yaw) + Math.abs(orbited.pitch - crossed.pitch),
  ).toBeGreaterThan(2);

  await wheelOnGraph(page, -120);
  const continuedValue = await steadyCamera(page);
  const continued = cameraSnapshot(continuedValue);
  expectForwardFlight(orbited, continued, 1);
  await page.waitForTimeout(1_500);
  expect(await copyCamera(page)).toBe(continuedValue);
});

test("WebKit accumulates fractional trackpad deltas and keeps pinch zoom native", async ({
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
  const canvas = graph.locator("canvas");

  for (let step = 0; step < 8; step += 1) {
    await canvas.dispatchEvent("wheel", { deltaY: -7.5, deltaMode: 0 });
  }
  const trackedValue = await steadyCamera(page);
  const tracked = cameraSnapshot(trackedValue);
  expectForwardFlight(initial, tracked, 1);

  await canvas.dispatchEvent("wheel", {
    deltaY: -120,
    deltaMode: 0,
    ctrlKey: true,
  });
  const pinched = cameraSnapshot(await steadyCamera(page));
  expect(length(targetDelta(tracked, pinched))).toBeLessThan(0.35);
  expect(pinched.yaw).toBeCloseTo(tracked.yaw, 0);
  expect(pinched.pitch).toBeCloseTo(tracked.pitch, 0);
  expect(Math.abs(pinched.radius - tracked.radius)).toBeGreaterThan(0.5);
});
