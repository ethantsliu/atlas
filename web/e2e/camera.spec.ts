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

async function readCameraWithoutInput(page: Page) {
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
  await expect(page.locator(".filters")).toContainText(
    "papers mapped by semantic similarity",
    {
      timeout: 20_000,
    },
  );
  const after = await steadyCamera(page);
  const movedParts = cameraParts(moved);
  const afterParts = cameraParts(after);
  expect(afterParts.slice(0, 4)).toEqual(movedParts.slice(0, 4));
  expect(Math.abs(afterParts[4] - movedParts[4])).toBeLessThanOrEqual(2);
  expect(Math.abs(afterParts[5] - movedParts[5])).toBeLessThanOrEqual(2);
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
  await expect.poll(() => readCameraWithoutInput(page), { timeout: 20_000 }).toBe(view);
  const initial = cameraSnapshot(view);

  let rotating = initial;
  await expect
    .poll(
      async () => {
        rotating = cameraSnapshot(await readCameraWithoutInput(page));
        return Math.abs(rotating.yaw - initial.yaw);
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(1);
  expect(length(targetDelta(initial, rotating))).toBeLessThan(0.35);
  expect(rotating.radius).toBeCloseTo(initial.radius, 1);
  expect(rotating.pitch).toBeCloseTo(initial.pitch, 0);

  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(800);
  const held = cameraSnapshot(await readCameraWithoutInput(page));
  await page.waitForTimeout(800);
  const stillHeld = cameraSnapshot(await readCameraWithoutInput(page));
  expectOrbitPreserved(held, stillHeld);
  expect(Math.abs(stillHeld.yaw - held.yaw)).toBeLessThanOrEqual(1);
  expect(length(targetDelta(held, stillHeld))).toBeLessThan(0.35);

  await page.mouse.up();
  await page.waitForTimeout(1_500);
  const released = cameraSnapshot(await readCameraWithoutInput(page));
  expectOrbitPreserved(stillHeld, released);
  expect(Math.abs(released.yaw - stillHeld.yaw)).toBeLessThanOrEqual(1);

  await expect
    .poll(
      async () => {
        const resumed = cameraSnapshot(await readCameraWithoutInput(page));
        return Math.abs(resumed.yaw - released.yaw);
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(1);

  const beforeWheel = cameraSnapshot(await readCameraWithoutInput(page));
  await wheelOnGraph(page, -120, 2, { x: 0.7, y: 0.35 });
  await page.waitForTimeout(800);
  const afterWheel = cameraSnapshot(await readCameraWithoutInput(page));
  expect(afterWheel.radius).toBeLessThan(beforeWheel.radius);
  await page.waitForTimeout(1_200);
  const wheelIdle = cameraSnapshot(await readCameraWithoutInput(page));
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
  await expect.poll(() => readCameraWithoutInput(page), { timeout: 20_000 }).toBe(view);
  await chooseAlignment(page);
  const center = page.getByRole("button", { name: "Center selected" });
  await expect(center).toBeVisible();

  const waiting = cameraSnapshot(await readCameraWithoutInput(page));
  await expect
    .poll(
      async () => {
        const rotating = cameraSnapshot(await readCameraWithoutInput(page));
        return Math.abs(rotating.yaw - waiting.yaw);
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(1);

  await center.focus();
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1_000);
  const centered = cameraSnapshot(await readCameraWithoutInput(page));
  await page.waitForTimeout(1_200);
  const held = cameraSnapshot(await readCameraWithoutInput(page));
  expectOrbitPreserved(centered, held);

  await expect
    .poll(
      async () => {
        const resumed = cameraSnapshot(await readCameraWithoutInput(page));
        return Math.abs(resumed.yaw - held.yaw);
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(1);
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
