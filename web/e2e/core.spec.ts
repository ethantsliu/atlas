import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { has3d } from "./capability";
import { archivePapers, fullNodes, mapStatus } from "./map";

const shard = /\/data\/papers\/[a-f0-9]{64}\.json(?:\?.*)?$/;

async function cloudLinks() {
  const root = join(process.cwd(), "public", "data", "cloud");
  const names = (await readdir(root)).filter((name) =>
    /^\d{4}-\d{2}\.json$/.test(name),
  );
  const links = new Map<string, string>();
  await Promise.all(
    names.map(async (name) => {
      const metadata = JSON.parse(await readFile(join(root, name), "utf8")) as {
        papers: string[][];
      };
      for (const paper of metadata.papers) links.set(paper[1], paper[2]);
    }),
  );
  return links;
}

async function cloudSize() {
  const root = join(process.cwd(), "public", "data", "cloud", "index.json");
  const manifest = JSON.parse(await readFile(root, "utf8")) as { count: number };
  return manifest.count;
}

type CloudTarget = {
  camera: string;
  point: readonly [number, number, number];
  title: string;
  url: string;
};

type CloudManifest = {
  count: number;
  shards: {
    count: number;
    meta: { path: string };
    points: { path: string };
  }[];
};

function cameraPart(value: number) {
  const rounded = Math.round(value * 10) / 10;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

function screenGap(points: Float32Array, candidate: number, other: Float32Array) {
  const at = candidate * 3;
  const aspect = 1.1;
  const radius = 16;
  const ndc = { x: 0.27, y: -0.21 };
  const tangent = Math.tan((50 * Math.PI) / 360);
  const distance = radius / tangent;
  const target = {
    x: points[at] - ndc.x * radius * aspect,
    y: points[at + 1] - ndc.y * radius,
    z: points[at + 2],
  };
  let gap = Number.POSITIVE_INFINITY;
  const visit = (points: Float32Array, skip = -1) => {
    for (let other = 0; other < points.length / 3; other += 1) {
      if (other === skip) continue;
      const offset = other * 3;
      const depth = target.z + distance - points[offset + 2];
      if (depth <= 0) continue;
      const scale = depth * tangent;
      const dx = (points[offset] - target.x) / (scale * aspect) - ndc.x;
      const dy = (points[offset + 1] - target.y) / scale - ndc.y;
      gap = Math.min(gap, dx * dx + dy * dy);
    }
  };
  visit(points, candidate);
  visit(other);
  return gap;
}

async function layoutPoints() {
  const root = join(process.cwd(), "public", "data");
  const core = JSON.parse(await readFile(join(root, "atlas.json"), "utf8")) as {
    layout: { positions: Record<string, number[]> };
    paper_asset: { path: string };
  };
  const paperPath = core.paper_asset.path.replace(/^\/data\//, "");
  const papers = JSON.parse(await readFile(join(root, paperPath), "utf8")) as {
    layout: { positions: Record<string, number[]> };
  };
  const rows = [
    ...Object.values(core.layout.positions),
    ...Object.values(papers.layout.positions),
  ];
  return Float32Array.from(rows.flatMap((row) => row.slice(0, 3)));
}

async function cloudLayout() {
  const root = join(process.cwd(), "public", "data", "cloud");
  const manifest = JSON.parse(
    await readFile(join(root, "index.json"), "utf8"),
  ) as CloudManifest;
  const blocks = await Promise.all(
    manifest.shards.map((shard) => readFile(join(root, shard.points.path))),
  );
  const positions = new Float32Array(manifest.count * 3);
  let next = 0;
  for (const [blockIndex, block] of blocks.entries()) {
    const count = block.readUInt32LE(8);
    if (count !== manifest.shards[blockIndex].count) {
      throw new Error("Historical point shard count drifted");
    }
    for (let index = 0; index < count * 3; index += 1) {
      positions[next * 3 + index] = block.readFloatLE(12 + index * 4);
    }
    next += count;
  }
  if (next !== manifest.count || manifest.shards.length === 0) {
    throw new Error("Historical point manifest count drifted");
  }
  return { manifest, positions, root };
}

async function cloudTarget(): Promise<CloudTarget> {
  const { manifest, positions, root } = await cloudLayout();
  const foreground = await layoutPoints();

  const stableSize = manifest.count >= 3_000_000 ? 100_000 : 0;
  const stableIds = stableSize
    ? Uint32Array.from({ length: stableSize }, (_, index) =>
        Math.floor(((index + 0.5) * manifest.count) / stableSize),
      )
    : null;
  const rendered = stableIds ? new Float32Array(stableIds.length * 3) : positions;
  stableIds?.forEach((index, sample) => {
    rendered.set(positions.subarray(index * 3, index * 3 + 3), sample * 3);
  });
  const last = manifest.shards.at(-1)!;
  const lastStart = manifest.count - last.count;
  const candidateCount = stableIds?.length ?? last.count;
  const samples = Math.min(128, candidateCount);
  let bestRendered = stableIds ? 0 : lastStart;
  let bestGap = -1;
  for (let sample = 0; sample < samples; sample += 1) {
    const local = Math.floor(
      (sample * (candidateCount - 1)) / Math.max(1, samples - 1),
    );
    const candidate = stableIds ? local : lastStart + local;
    const gap = screenGap(rendered, candidate, foreground);
    if (gap > bestGap) {
      bestRendered = candidate;
      bestGap = gap;
    }
  }

  const best = stableIds?.[bestRendered] ?? bestRendered;
  let start = 0;
  const shard = manifest.shards.find((candidate) => {
    if (best < start + candidate.count) return true;
    start += candidate.count;
    return false;
  });
  if (!shard) throw new Error("Historical target is outside its manifest");
  const local = best - start;
  const metadata = JSON.parse(await readFile(join(root, shard.meta.path), "utf8")) as {
    papers: string[][];
  };
  const row = metadata.papers[local];
  if (!row?.[1] || !row[2]) throw new Error("Historical target metadata is missing");
  const at = best * 3;
  const camera = `1_${cameraPart(positions[at])}_${cameraPart(
    positions[at + 1],
  )}_${cameraPart(positions[at + 2])}_16_0_0`;
  return {
    camera,
    point: [positions[at], positions[at + 1], positions[at + 2]],
    title: row[1],
    url: row[2],
  };
}

async function foregroundTarget(): Promise<CloudTarget> {
  const root = join(process.cwd(), "public", "data");
  const core = JSON.parse(await readFile(join(root, "atlas.json"), "utf8")) as {
    layout: { positions: Record<string, number[]> };
    paper_asset: { path: string };
  };
  const path = core.paper_asset.path.replace(/^\/data\//, "");
  const bundle = JSON.parse(await readFile(join(root, path), "utf8")) as {
    layout: { positions: Record<string, number[]> };
    papers: { id: string; title: string; url: string }[];
  };
  const coreRows = Object.values(core.layout.positions);
  const paperRows = Object.entries(bundle.layout.positions);
  const foreground = Float32Array.from(
    [...coreRows, ...paperRows.map(([, row]) => row)].flatMap((row) => row.slice(0, 3)),
  );
  const { positions: cloud } = await cloudLayout();
  const samples = Math.min(128, paperRows.length);
  let best = 0;
  let bestGap = -1;
  for (let sample = 0; sample < samples; sample += 1) {
    const index = Math.floor(
      (sample * (paperRows.length - 1)) / Math.max(1, samples - 1),
    );
    const gap = screenGap(foreground, coreRows.length + index, cloud);
    if (gap > bestGap) {
      best = index;
      bestGap = gap;
    }
  }
  const [id, row] = paperRows[best];
  const paper = bundle.papers.find((entry) => entry.id === id);
  if (!paper || row.length < 3)
    throw new Error("Foreground target metadata is missing");
  return {
    camera: `1_${cameraPart(row[0])}_${cameraPart(row[1])}_${cameraPart(row[2])}_16_0_0`,
    point: [row[0], row[1], row[2]],
    title: paper.title,
    url: paper.url,
  };
}

function offsetCamera(target: CloudTarget, aspect: number) {
  const radius = 16;
  const intended = { x: 0.27, y: -0.21 };
  const [x, y, z] = target.point;
  const view = {
    x: Number(cameraPart(x - intended.x * radius * aspect)),
    y: Number(cameraPart(y - intended.y * radius)),
    z: Number(cameraPart(z)),
  };
  const tangent = Math.tan((50 * Math.PI) / 360);
  const depth = view.z + radius / tangent - z;
  const ndc = {
    x: (x - view.x) / (depth * tangent * aspect),
    y: (y - view.y) / (depth * tangent),
  };
  const camera = `1_${view.x}_${view.y}_${view.z}_${radius}_0_0`;
  return { camera, ndc };
}

function trackShard(page: Page): string[] {
  const hits: string[] = [];
  page.on("request", (request) => {
    if (shard.test(request.url())) hits.push(request.url());
  });
  return hits;
}

async function showFilters(page: Page) {
  const toggle = page.locator(".mobile-filter-toggle");
  if (await toggle.isVisible()) await toggle.click();
}

async function chooseTopic(page: Page) {
  const picker = page
    .getByRole("combobox", { name: "Choose a visible graph node" })
    .and(page.locator("input"));
  await expect(picker).toHaveAttribute("placeholder", "Find a node…", {
    timeout: 20_000,
  });
  await picker.fill("pretraining");
  await page.getByRole("option", { name: /Topic\s+pretraining/i }).click();
}

async function loadMap(page: Page, path = "/#?k=tri") {
  await page.goto(path);
  await expect(page.getByLabel(/Interactive (3D )?research graph/)).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByLabel("Choose a visible graph node")).toBeAttached();
}

async function scanAxe(page: Page) {
  const report = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(report.violations).toEqual([]);
}

async function otherNode(
  page: Page,
  box: { x: number; y: number; width: number; height: number },
  blocked: string,
  kind?: "Topic" | "Trick" | "Paper" | "Idea",
  anchor?: { x: number; y: number },
) {
  const tips = page.locator(
    ".core-tip:visible, .swarm-tip:visible, .float-tooltip-kap:visible",
  );
  const offsets = [0, -24, 24, -48, 48, -96, 96];
  const center = anchor ?? {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  };
  const points = offsets.flatMap((y) =>
    offsets.map((x) => ({
      x: center.x + x,
      y: center.y + y,
    })),
  );
  for (const y of [0.25, 0.4, 0.6, 0.75]) {
    for (const x of [0.2, 0.35, 0.5, 0.65, 0.8]) {
      points.push({ x: box.x + box.width * x, y: box.y + box.height * y });
    }
  }
  for (const point of points) {
    await page.mouse.move(point.x, point.y);
    await page.waitForTimeout(350);
    if ((await tips.allTextContents()).includes("Loading Paper…")) {
      await expect
        .poll(async () => (await tips.allTextContents()).includes("Loading Paper…"), {
          timeout: 10_000,
        })
        .toBe(false);
    }
    const entry = (
      await tips.evaluateAll((elements) =>
        elements.map((element) => {
          const depth = Number((element as HTMLElement).dataset.depth);
          return {
            depth: Number.isFinite(depth) ? depth : 0,
            label: element.textContent ?? "",
          };
        }),
      )
    ).find(
      ({ label }) =>
        /^(Topic|Trick|Paper|Idea) · /.test(label) &&
        (!kind || label.startsWith(`${kind} · `)) &&
        !label.includes(blocked),
    );
    if (entry) return { ...point, ...entry };
  }
  throw new Error(`No visible node appeared over ${blocked}`);
}

async function cloudPoint(
  page: Page,
): Promise<{ x: number; y: number; title: string }> {
  const graph = page.getByLabel("Interactive 3D research graph");
  const box = await graph.boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const tip = page.locator(".cloud-tip");
  const core = page.locator(".swarm-tip:not(.cloud-tip)");
  for (const y of [0.45, 0.55, 0.65, 0.75, 0.35]) {
    for (const x of [0.25, 0.4, 0.55, 0.7, 0.8]) {
      const point = { x: box.x + box.width * x, y: box.y + box.height * y };
      await page.mouse.move(point.x, point.y);
      await page.waitForTimeout(350);
      let label = (await tip.count()) ? await tip.textContent() : null;
      if (label === "Loading Paper…") {
        await page.waitForTimeout(700);
        label = (await tip.count()) ? await tip.textContent() : null;
      }
      if (label?.startsWith("Paper · ") && (await core.count()) === 0) {
        return { ...point, title: label.slice("Paper · ".length) };
      }
    }
  }
  throw new Error("No historical paper point accepted hover input");
}

async function watchCopy(page: Page) {
  await page.addInitScript(() => {
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

async function copiedCamera(page: Page, input = false) {
  const copy = page.getByRole("button", { name: "Copy a link to this atlas view" });
  if (input) await copy.click();
  else await copy.evaluate((button: HTMLButtonElement) => button.click());
  const copied = await page.evaluate(
    () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
  );
  return copied
    ? new URLSearchParams(new URL(copied).hash.replace(/^#\?/, "")).get("c")
    : null;
}

async function waitCamera(page: Page, camera: string) {
  const read = () => copiedCamera(page, true);
  await expect.poll(read, { timeout: 20_000 }).toBe(camera);
  await page.waitForTimeout(120);
  await expect.poll(read, { timeout: 20_000 }).toBe(camera);
}

async function waitCameraIdle(page: Page) {
  const copy = page.getByRole("button", { name: "Copy a link to this atlas view" });
  const read = async () => {
    await copy.evaluate((button: HTMLButtonElement) => button.click());
    const copied = await page.evaluate(
      () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
    );
    return copied
      ? new URLSearchParams(new URL(copied).hash.replace(/^#\?/, "")).get("c")
      : null;
  };
  const deadline = Date.now() + 30_000;
  let camera = await read();
  let unchangedSince = Date.now();
  while (Date.now() < deadline) {
    await page.waitForTimeout(250);
    const current = await read();
    if (current !== camera) {
      camera = current;
      unchangedSince = Date.now();
    } else if (camera && Date.now() - unchangedSince >= 1_000) {
      return camera;
    }
  }
  throw new Error("Research graph camera did not settle");
}

test("the initial map enables every lens", async ({ page }) => {
  const hits = trackShard(page);
  await loadMap(page, "/");
  await showFilters(page);
  await expect(page.locator('.filters .kind-toggle[aria-pressed="true"]')).toHaveCount(
    4,
    { timeout: 20_000 },
  );
  await fullNodes(page);
  await expect(page.getByRole("button", { name: /Papers\s+[,\d]+/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(hits).toHaveLength(1);
});

test("history streams points without eager paper metadata", async ({ page }) => {
  const points: string[] = [];
  const metadata: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (/\/data\/cloud\/(?:\d{4}-\d{2}|p\d{3,})\.bin(?:\?.*)?$/.test(url)) {
      points.push(url);
    }
    if (/\/data\/cloud\/\d{4}-\d{2}\.json(?:\?.*)?$/.test(url)) metadata.push(url);
  });
  await loadMap(page, "/#?d=3");
  test.skip(!(await has3d(page)), "History streaming requires WebGL2");
  await showFilters(page);
  await fullNodes(page);
  await expect.poll(() => points.length).toBeGreaterThan(0);
  expect(metadata).toEqual([]);
});

test("the paper lens fetches its shard once", async ({ page }) => {
  test.setTimeout(90_000);
  const hits = trackShard(page);
  await loadMap(page);
  await showFilters(page);
  const lens = page.getByRole("button", {
    name: /Papers\s+[,\d]+/,
  });
  await lens.click();
  await fullNodes(page);
  expect(hits).toHaveLength(1);

  await lens.click();
  await lens.click();
  await fullNodes(page);
  expect(hits).toHaveLength(1);
});

test("search fetches the paper shard once", async ({ page }) => {
  const hits = trackShard(page);
  await loadMap(page);
  await page.getByLabel("Search the atlas").fill("hemispheric redundancy");
  await expect(mapStatus(page)).toContainText(/visible graph nodes? match/);
  await expect(mapStatus(page)).not.toContainText("0 visible");
  expect(hits).toHaveLength(1);
});

test("a bare paper deep link selects it and opens evidence explicitly", async ({
  page,
}) => {
  const hits = trackShard(page);
  await loadMap(page, "/#?s=paper-1");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue(
    /In Two Minds|paper-1/,
  );
  await expect(page.getByRole("heading", { name: "In Two Minds" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Open paper", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("In Two Minds", {
    timeout: 20_000,
  });
  expect(hits).toHaveLength(1);
});

test("hover labels a node and click keeps details in the inspector", async ({
  page,
}, testInfo) => {
  test.skip(["android", "iphone"].includes(testInfo.project.name));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1_440, height: 900 });
  await loadMap(page);
  test.skip(!(await has3d(page)), "3D hover requires WebGL2");
  await showFilters(page);
  const fullState = await fullNodes(page);
  await chooseTopic(page);
  await page.getByRole("button", { name: "Isolate connections" }).click();
  await expect(mapStatus(page)).not.toHaveText(fullState!);
  await page.waitForTimeout(2_500);
  await page.getByRole("button", { name: "Center selected" }).click();

  const graph = page.getByLabel(/Interactive (3D )?research graph/);
  const box = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const toolbar = await page.locator(".graph-toolbar").boundingBox();
  const centerY = box.y + box.height / 2;
  const entry = await otherNode(page, box, "^@", undefined, {
    x: box.x + box.width / 2,
    y: Math.max(centerY, toolbar ? toolbar.y + toolbar.height + 12 : centerY),
  });
  const tooltip = page
    .locator(".core-tip:visible, .swarm-tip:visible, .float-tooltip-kap:visible")
    .filter({ hasText: entry.label })
    .first();
  await expect(tooltip).toContainText(entry.label);
  await expect(tooltip).toHaveCSS("font-family", /Baskerville/);
  await expect(tooltip).toHaveCSS("font-size", "14px");
  await page.mouse.down();
  await page.mouse.up();
  const title = entry.label.replace(/^\w+\s·\s/, "");
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const inspector = await page.locator("#map-inspector").boundingBox();
  if (!inspector) throw new Error("Node inspector has no bounds");
  expect(inspector.x).toBeGreaterThanOrEqual(box.x + box.width - 2);
  expect(inspector.width).toBeGreaterThanOrEqual(280);
  expect(inspector.width).toBeLessThanOrEqual(520);
  await page.mouse.move(box.x + 12, box.y + 12);
  await expect(tooltip).toBeHidden();
});

test("historical paper points open the inline inspector", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Historical point picking is covered in Chromium and WebKit",
  );
  let metaTry = 0;
  await page.route(/\/data\/cloud\/\d{4}-\d{2}\.json(?:\?.*)?$/, async (route) => {
    metaTry += 1;
    if (metaTry === 1) {
      await new Promise((resolve) => setTimeout(resolve, 900));
      await route.fulfill({ contentType: "text/html", body: "<!doctype html>" });
      return;
    }
    await route.fulfill({ response: await route.fetch() });
  });
  await page.setViewportSize({ width: 1_440, height: 900 });
  const size = await cloudSize();
  const target = size > 100_000 ? await cloudTarget() : null;
  if (target) await watchCopy(page);
  const links = target ? null : await cloudLinks();
  await page.goto(target ? `/#?k=p&c=${target.camera}` : "/#?d=3");
  await archivePapers(page);
  if (target) await waitCamera(page, target.camera);
  await page.waitForTimeout(2_500);
  if (target) {
    // A hardware renderer may now orbit continuously; a slow/software
    // renderer deliberately stays still after its full-cloud frame benchmark.
    // Both paths retain this exact paper-centered target for the hover check.
    expect(await copiedCamera(page)).toBeTruthy();
  }
  const graph = page.getByLabel("Interactive 3D research graph");
  const inspector = page.locator("#map-inspector");
  const beforeGraph = await graph.boundingBox();
  const beforePanel = await inspector.boundingBox();
  const fullState = await fullNodes(page);
  let title: string;
  if (!target) {
    const point = await cloudPoint(page);
    const tip = page.locator(".cloud-tip");
    await expect(tip).toHaveCSS("font-family", /Baskerville/);
    await expect(tip).toHaveCSS("font-size", "14px");
    await expect(tip).toContainText(`Paper · ${point.title}`);
    await page.mouse.click(point.x, point.y);
    title = point.title;
  } else {
    if (!beforeGraph) throw new Error("Research graph has no bounds");
    const canvasBox = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
    if (!canvasBox) throw new Error("Research graph canvas has no bounds");
    const center = {
      x: canvasBox.x + canvasBox.width / 2,
      y: canvasBox.y + canvasBox.height / 2,
    };
    const tip = page.locator(".cloud-tip");
    await page.mouse.move(center.x, center.y);
    await expect(tip).toBeVisible({ timeout: 20_000 });
    await expect(tip).not.toContainText("Loading Paper…", { timeout: 20_000 });
    if ((await tip.textContent())?.includes("unavailable")) {
      await page.mouse.move(2, 2);
      await page.waitForTimeout(180);
      await page.mouse.move(center.x, center.y);
    }
    await expect(tip).toContainText(`Paper · ${target.title}`, {
      timeout: 20_000,
    });

    await page.mouse.down();
    await page.mouse.move(center.x + 5, center.y + 3);
    await expect(tip).toBeHidden();
    await page.mouse.up();

    const offset = offsetCamera(target, canvasBox.width / canvasBox.height);
    await page.goto(`/?pick=offset#?k=p&c=${offset.camera}`);
    await archivePapers(page);
    await waitCamera(page, offset.camera);
    const offsetBox = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
    if (!offsetBox) throw new Error("Research graph canvas has no bounds");
    const point = {
      x: offsetBox.x + ((offset.ndc.x + 1) * offsetBox.width) / 2,
      y: offsetBox.y + ((1 - offset.ndc.y) * offsetBox.height) / 2,
    };
    await page.mouse.move(point.x, point.y);
    await expect(tip).toContainText(`Paper · ${target.title}`, {
      timeout: 20_000,
    });
    await page.mouse.click(point.x, point.y);
    await expect(inspector.getByRole("heading", { name: target.title })).toBeVisible({
      timeout: 20_000,
    });
    title = target.title;
  }
  await page.mouse.move(2, 2);

  await expect(inspector.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.locator("#graph-selection")).toHaveText(`Paper selected: ${title}`);
  expect(await graph.boundingBox()).toEqual(beforeGraph);
  expect(await inspector.boundingBox()).toEqual(beforePanel);
  await expect(inspector.getByRole("link", { name: "View on arXiv" })).toHaveAttribute(
    "href",
    target?.url ?? links?.get(title) ?? "missing historical paper link",
  );
  await expect(inspector.locator("time")).toHaveAttribute(
    "datetime",
    /^\d{4}-\d{2}-\d{2}/,
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const graphBox = await graph.boundingBox();
  const panelBox = await inspector.boundingBox();
  const isolate = page.getByRole("button", { name: "Isolate connections" });
  await expect(isolate).toBeEnabled();
  await isolate.click();
  await expect(
    page.getByRole("button", { name: "Unisolate connections" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(inspector).toContainText("Exact MiniLM cosine anchors", {
    timeout: 20_000,
  });
  await expect(mapStatus(page)).toHaveText("9 visible graph nodes available.");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await graph.boundingBox()).toEqual(graphBox);
  expect(await inspector.boundingBox()).toEqual(panelBox);
  await page.getByRole("button", { name: "Unisolate connections" }).click();
  await expect(isolate).toHaveAttribute("aria-pressed", "false");
  await expect(mapStatus(page)).toHaveText(fullState);
  await expect(inspector.getByRole("heading", { name: title })).toBeVisible();

  const picker = page.getByLabel("Choose a visible graph node");
  await page.getByRole("button", { name: /Topics\s+17/ }).click();
  await picker.fill("pretraining");
  await page.getByRole("option", { name: /Topic\s+pretraining/i }).click();
  await expect(inspector.getByRole("heading", { name: "pretraining" })).toBeVisible();
  await expect(inspector.getByRole("link", { name: "View on arXiv" })).toHaveCount(0);
});

test("the nearest visible layer wins at one exact pointer coordinate", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Layered 3D picking is covered in Chromium and WebKit",
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1_440, height: 900 });
  await watchCopy(page);
  await loadMap(page, "/#?s=topic%3Aalignment&k=trpi");
  const size = await cloudSize();
  await archivePapers(page);
  await fullNodes(page);
  const inspector = page.locator("#map-inspector");
  await expect(inspector.getByRole("heading", { name: "alignment" })).toBeVisible();
  await waitCameraIdle(page);
  const center = page.getByRole("button", { name: "Center selected" });

  const graph = page.getByLabel("Interactive 3D research graph");
  const box = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  const tips = page.locator(".core-tip:visible, .swarm-tip:visible");
  await expect
    .poll(
      async () => {
        await page.mouse.move(2, 2);
        await center.click();
        await page.mouse.move(point.x, point.y);
        await page.waitForTimeout(820);
        return tips.count();
      },
      {
        message: "centered selection should settle under the pointer",
        timeout: 30_000,
      },
    )
    .toBe(1);
  await expect(tips).not.toContainText("Loading Paper…", { timeout: 20_000 });
  const camera = await waitCameraIdle(page);
  await expect
    .poll(
      async () => {
        await page.mouse.move(2, 2);
        await page.mouse.move(point.x, point.y);
        await page.waitForTimeout(820);
        return tips.count();
      },
      { timeout: 30_000 },
    )
    .toBe(1);
  await expect(tips).not.toContainText("Loading Paper…", { timeout: 20_000 });
  const radius = Number(camera?.split("_")[4]);
  expect(radius).toBeGreaterThan(0);
  const rearDepth = radius / Math.tan((50 * Math.PI) / 360);

  const front = await tips.evaluateAll((elements) =>
    elements.map((element) => ({
      depth: Number((element as HTMLElement).dataset.depth),
      label: element.textContent ?? "",
    })),
  );
  expect(front).toHaveLength(1);
  const match = front[0].label.match(/^(Topic|Trick|Paper|Idea) · (.+)$/);
  expect(match).not.toBeNull();
  if (match?.[1] === "Topic" && match[2] === "alignment") {
    // Camera links quantize position and radius to tenths. Radius error is
    // magnified by the perspective conversion, so include both serialization
    // bounds instead of comparing the target strictly against its own depth.
    expect(Math.abs(front[0].depth - rearDepth)).toBeLessThan(0.3);
  } else {
    // Any different layer accepted at this exact coordinate must genuinely be
    // in front of the centered alignment target.
    expect(front[0].depth).toBeLessThan(rearDepth);
  }

  const [, kind, title] = match!;
  await page.mouse.click(point.x, point.y);
  await expect(page.locator("#graph-selection")).toHaveText(
    `${kind} selected: ${title}`,
    { timeout: 20_000 },
  );
  await expect(inspector.getByRole("heading", { name: title })).toBeVisible({
    timeout: 20_000,
  });
});

test("core gestures preserve picking after camera movement", async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Core gesture settlement is covered in Chromium and WebKit",
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1_440, height: 900 });
  await loadMap(page, "/#?s=topic%3Apre-training&k=tri&l=c");
  await expect(mapStatus(page)).toContainText("visible graph nodes available");
  await page.waitForTimeout(2_500);
  const graph = page.getByLabel("Interactive 3D research graph");
  const box = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
  if (!box) throw new Error("Research graph has no bounds");
  const inspector = page.locator("#map-inspector");
  await page.getByRole("button", { name: "Center selected" }).click();
  await page.waitForTimeout(300);

  const first = await otherNode(page, box, "^@");
  expect(first.depth).toBeGreaterThan(0);
  const firstTitle = first.label.replace(/^\w+\s·\s/, "");
  await page.mouse.click(first.x, first.y);
  await expect(inspector.getByRole("heading", { name: firstTitle })).toBeVisible();

  await page.mouse.wheel(0, 1_200);
  await page.waitForTimeout(300);
  const second = await otherNode(page, box, firstTitle);
  const title = second.label.replace(/^\w+\s·\s/, "");
  await page.mouse.click(second.x, second.y);
  await expect(inspector.getByRole("heading", { name: title })).toBeVisible({
    timeout: 20_000,
  });
});

test("touch opens a historical paper in the stacked inspector", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  test.skip(testInfo.project.name !== "iphone", "Dense touch picking uses iPhone");
  test.skip((await cloudSize()) <= 100_000, "Dense cloud touch needs the full corpus");
  const target = await cloudTarget();
  await watchCopy(page);
  await page.goto(`/#?k=p&c=${target.camera}`);
  await archivePapers(page);
  await fullNodes(page);

  const graph = page.getByLabel("Interactive 3D research graph");
  await waitCamera(page, target.camera);
  await expect(
    page.getByRole("group", { name: "historical paper dot density" }),
  ).toHaveCount(0);

  const inspector = page.locator("#map-inspector");
  const beforeGraph = await graph.boundingBox();
  if (!beforeGraph) throw new Error("Research graph has no bounds");
  const selection = page.locator("#graph-selection");
  const canvas = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
  if (!canvas) throw new Error("Research graph canvas has no bounds");
  const cloudSource = inspector.getByRole("link", { name: "View on arXiv" });
  await page.waitForTimeout(900);
  await page.touchscreen.tap(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);

  await expect(inspector.getByRole("heading", { name: target.title })).toBeVisible({
    timeout: 20_000,
  });
  await expect(cloudSource).toHaveAttribute("href", target.url);
  await expect(inspector).toHaveAccessibleName(target.title);
  await expect(selection).toHaveText(`Paper selected: ${target.title}`);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const afterGraph = await graph.boundingBox();
  expect(afterGraph?.x).toBe(beforeGraph.x);
  expect(afterGraph?.width).toBe(beforeGraph.width);
  await expect
    .poll(async () => (await inspector.boundingBox())?.y ?? Number.POSITIVE_INFINITY)
    .toBeLessThan(testInfo.project.use.viewport?.height ?? 840);
  await expect(inspector).toBeFocused();
  expect(
    await page.evaluate(() => {
      const graph = document.querySelector(".graph-wrap");
      const inspector = document.getElementById("map-inspector");
      return Boolean(
        graph &&
        inspector &&
        graph.compareDocumentPosition(inspector) & Node.DOCUMENT_POSITION_FOLLOWING,
      );
    }),
  ).toBe(true);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    )
    .toBe(true);

  const fullState = await fullNodes(page);
  await page.getByRole("button", { name: "Isolate connections" }).click();
  await expect(mapStatus(page)).toHaveText("9 visible graph nodes available.");
  const unisolate = page.getByRole("button", { name: "Unisolate connections" });
  await expect(unisolate).toHaveAttribute("aria-pressed", "true");
  await unisolate.click();
  await expect(mapStatus(page)).toHaveText(fullState);
  await expect(inspector.getByRole("heading", { name: target.title })).toBeVisible();
});

test("foreground selection opens the stacked inspector", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "iphone", "Stacked focus uses iPhone");
  await loadMap(page);
  await chooseTopic(page);
  const inspector = page.locator("#map-inspector");
  await expect(inspector).toBeFocused();
  await expect(inspector).toHaveAccessibleName("pretraining");
  await expect
    .poll(async () => (await inspector.boundingBox())?.y ?? Number.POSITIVE_INFINITY)
    .toBeLessThan(testInfo.project.use.viewport?.height ?? 840);
});

test("foreground paper points open the visible paper", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  test.skip(
    !["chrome", "safari"].includes(testInfo.project.name),
    "Foreground point picking requires hosted 3D support",
  );
  await page.setViewportSize({ width: 1_440, height: 900 });
  const target = await foregroundTarget();
  await watchCopy(page);
  await page.goto("/#?d=3");
  await archivePapers(page);
  await page.waitForTimeout(2_500);

  const graph = page.getByLabel("Interactive 3D research graph");
  const firstCanvas = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
  if (!firstCanvas) throw new Error("Research graph canvas has no bounds");
  const offset = offsetCamera(target, firstCanvas.width / firstCanvas.height);
  await page.goto(`/?pick=foreground#?d=3&c=${offset.camera}`);
  await archivePapers(page);
  await waitCamera(page, offset.camera);
  const graphBox = await graph.boundingBox();
  const panel = page.locator("#map-inspector");
  const panelBox = await panel.boundingBox();
  const canvas = await graph.locator("canvas:not(.cloud-plane)").boundingBox();
  if (!canvas) throw new Error("Research graph canvas has no bounds");
  const point = {
    x: canvas.x + ((offset.ndc.x + 1) * canvas.width) / 2,
    y: canvas.y + ((1 - offset.ndc.y) * canvas.height) / 2,
  };
  await page.mouse.move(point.x, point.y);
  const tip = page.locator(".swarm-tip:not(.cloud-tip)");
  await expect(tip).toContainText(`Paper · ${target.title}`, { timeout: 20_000 });
  await expect(page.locator(".cloud-tip")).toHaveCount(0);
  await page.mouse.click(point.x, point.y);

  const inspector = panel;
  await expect(inspector.getByRole("heading", { name: target.title })).toBeVisible();
  await expect(inspector.getByRole("button", { name: "Open paper" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await graph.boundingBox()).toEqual(graphBox);
  expect(await inspector.boundingBox()).toEqual(panelBox);
});

test("2D hover and click use the same inline inspector", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  test.skip(["android", "iphone"].includes(testInfo.project.name));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1_440, height: 900 });
  await loadMap(page, "/#?d=2&k=tri");
  const plane = page.locator(".cloud-plane");
  await expect(plane).toHaveAttribute("data-engine", /^(ready|unsupported)$/, {
    timeout: 20_000,
  });
  test.skip(
    (await plane.getAttribute("data-engine")) !== "ready",
    "2D archive interaction requires WebGL2",
  );
  await showFilters(page);
  await page.getByRole("button", { name: /Papers\s+[,\d]+/ }).click();
  const picker = page.getByLabel("Choose a visible graph node");
  const filters = page.locator(".filters");
  await expect(filters).toContainText("papers mapped");
  const fullState = await fullNodes(page);
  const fullCount = Number(fullState.match(/[\d,]+/)?.[0].replaceAll(",", ""));
  expect(fullCount).toBeGreaterThan(200_000);
  await expect(page.locator(".graph-header")).toContainText(
    `${fullCount.toLocaleString()} nodes`,
  );
  await picker.fill("In-Context Language Learning");
  await page.getByRole("option", { name: /In-Context Language Learning/ }).click();
  await page.getByRole("button", { name: "Isolate connections" }).click();
  await expect(mapStatus(page)).not.toHaveText(fullState!);
  const isolatedOptions = await picker.locator("option").count();
  const isolatedCount = Number(
    (await mapStatus(page).textContent())?.match(/[\d,]+/)?.[0].replaceAll(",", ""),
  );
  expect(isolatedCount).toBe(isolatedOptions - 1);
  await page.waitForTimeout(2_500);
  await page.getByRole("button", { name: "Center selected" }).click();

  const graph = page.getByLabel("Interactive research graph");
  const box = await graph.boundingBox();
  if (!box) throw new Error("2D research graph has no bounds");
  const entry = await otherNode(page, box, "^@", "Paper");
  const tooltip = page
    .locator(".core-tip:visible, .swarm-tip:visible, .float-tooltip-kap:visible")
    .filter({ hasText: entry.label })
    .first();
  await expect(tooltip).toContainText(entry.label);
  await expect(tooltip).toHaveCSS("font-family", /Baskerville/);
  await page.mouse.click(entry.x, entry.y);
  const title = entry.label.replace(/^\w+\s·\s/, "");
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Unisolate connections" })
    .evaluate((button: HTMLButtonElement) => button.click());
  await expect(mapStatus(page)).toHaveText(fullState);
});

test("copied view links include a camera snapshot", async ({ page, context }) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
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
  await loadMap(page);
  await showFilters(page);
  await page.getByRole("button", { name: /Papers\s+[,\d]+/ }).click();
  await fullNodes(page);
  const header = page.locator(".graph-header > div");
  await expect(header).toContainText(/[,\d]+ nodes/, { timeout: 20_000 });
  await expect(header).not.toContainText("drawn");
  const picker = page.getByLabel("Choose a visible graph node");
  await picker.fill("Massive Spikes in LLMs are Bias Vectors");
  await page.getByRole("option", { name: /Massive Spikes in LLMs/ }).click();
  await expect(header).toContainText(/[,\d]+ nodes/);
  await page.getByRole("button", { name: "Center selected" }).click();
  await page.getByRole("button", { name: "Copy a link to this atlas view" }).click();
  const copied = await page.evaluate(
    () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
  );
  const cameraValue = new URLSearchParams(new URL(copied).hash.replace(/^#\?/, "")).get(
    "c",
  );
  const camera = cameraValue?.replace(/^1_/, "").split("_").map(Number);
  const selectedId = new URLSearchParams(
    new URL(page.url()).hash.replace(/^#\?/, ""),
  ).get("s");
  if (!selectedId) throw new Error("Selected paper is missing from the atlas URL");
  expect(camera).toHaveLength(6);
  expect(camera?.every(Number.isFinite)).toBe(true);
  const shared = await context.newPage();
  await shared.goto(copied);
  await expect(shared.getByLabel("Choose a visible graph node")).toHaveValue(
    /Massive Spikes in LLMs/,
  );
  expect(
    new URLSearchParams(new URL(shared.url()).hash.replace(/^#\?/, "")).get("s"),
  ).toBe(selectedId);
  await expect(shared.getByLabel(/Interactive (3D )?research graph/)).toBeVisible();
  await shared.waitForTimeout(500);
  await shared.getByRole("button", { name: "Copy a link to this atlas view" }).click();
  const restored = await shared.evaluate(
    () => (window as typeof window & { __atlasCopied?: string }).__atlasCopied ?? "",
  );
  expect(new URLSearchParams(new URL(restored).hash.replace(/^#\?/, "")).get("c")).toBe(
    cameraValue,
  );
  await shared.close();
});

test("a failed paper shard retries once", async ({ page }) => {
  let attempts = 0;
  await page.route("**/data/papers/*.json", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, body: "Unavailable" });
      return;
    }
    await route.continue();
  });

  await loadMap(page);
  await page.getByLabel("Search the atlas").fill("hemispheric redundancy");
  await expect(page.getByRole("alert")).toContainText(
    "Paper index unavailable: Paper asset request failed (503)",
  );
  await page.getByRole("button", { name: "Retry papers" }).click();
  await expect(mapStatus(page)).toContainText(/visible graph nodes? match/);
  await expect(mapStatus(page)).not.toContainText("0 visible");
  expect(attempts).toBe(2);
});

test("URL state hydrates all map controls", async ({ page }) => {
  await loadMap(
    page,
    "/#?q=alignment&s=topic%3Aalignment&k=ti&f=5.5&x=topic%3Aalignment&l=c",
  );
  await showFilters(page);

  await expect(page.getByLabel("Search the atlas")).toHaveValue("alignment");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue(
    "topic:alignment",
  );
  await expect(page.getByLabel("Minimum feasibility")).toHaveValue("5.5");
  await expect(
    page.getByRole("button", { name: "connections", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const filters = page.locator(".filters");
  await expect(filters.getByRole("button", { name: /^Topics\s/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(filters.getByRole("button", { name: /^Techniques\s/ })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("history restores pushed views", async ({ page }) => {
  await loadMap(page);
  await page.getByRole("button", { name: "Daily", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Daily", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "Library", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "Collection entry library" }),
  ).toBeVisible();

  await page.goBack();
  await expect(
    page.getByRole("button", { name: "Daily", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.goForward();
  await expect(
    page.getByRole("button", { name: "Library", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});

test("invalid IDs are discarded safely", async ({ page }) => {
  const hits = trackShard(page);
  await loadMap(page, "/#?s=%3Cscript%3E&x=bad%20id&k=tt&f=99");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue("");
  await expect(page.getByLabel("Minimum feasibility")).toHaveValue("1");
  await page.waitForTimeout(250);
  expect(hits).toHaveLength(1);

  await page.goto("/#?s=missing-node");
  await expect(page.getByLabel("Choose a visible graph node")).toHaveValue("");
  await expect.poll(() => page.url()).not.toContain("s=missing-node");
});

test("clipboard failure is announced", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: () => Promise.reject(new Error("denied")) },
    });
  });
  await loadMap(page);
  const copy = page.getByRole("button", { name: "Copy a link to this atlas view" });
  await copy.click();
  await expect(copy).toContainText("Try again");
  await expect(page.locator(".share-link").getByRole("status")).toContainText(
    "Atlas link could not be copied",
  );
});

test("nearby nodes support keyboard entry", async ({ page }) => {
  await loadMap(page, "/#?s=topic%3Aalignment");
  await fullNodes(page);
  const nearby = page.locator(".nearby").getByRole("button").first();
  const initial = await page.getByLabel("Choose a visible graph node").inputValue();
  await nearby.focus();
  await expect(nearby).toBeFocused();
  await page.keyboard.press("Enter");
  await expect
    .poll(async () => {
      const selected = await page
        .getByLabel("Choose a visible graph node")
        .inputValue();
      return selected !== initial || (await page.getByRole("dialog").count()) > 0;
    })
    .toBe(true);
});

test("the graph has no ambient labels", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
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
  await loadMap(page);
  const tooltip = page.locator(".float-tooltip-kap");
  await expect(tooltip).toBeHidden();

  await page.getByLabel("Search the atlas").fill("alignment");
  await expect(tooltip).toBeHidden();
  await page.getByLabel("Search the atlas").fill("");
  await page.getByRole("button", { name: "connections", exact: true }).click();
  await expect(tooltip).toBeHidden();
});

test("details panel resizes and returns to its default", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loadMap(page);
  const separator = page.getByRole("separator", { name: "Resize details panel" });
  const inspector = page.locator("#map-inspector");
  await expect(separator).toBeVisible();
  await expect(separator).toHaveAttribute("aria-valuenow", "330");

  await separator.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(separator).toHaveAttribute("aria-valuenow", "346");
  await expect
    .poll(async () => Math.round((await inspector.boundingBox())?.width ?? 0))
    .toBe(346);

  const box = await separator.boundingBox();
  if (!box) throw new Error("Resize separator has no bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + 180);
  await page.mouse.down();
  await page.mouse.move(box.x - 64, box.y + 180, { steps: 4 });
  await page.mouse.up();
  const stored = Number(await separator.getAttribute("aria-valuenow"));
  expect(stored).toBeGreaterThan(346);
  await page.reload();
  await expect(separator).toHaveAttribute("aria-valuenow", String(stored));
  expect(page.url()).not.toContain("panel");

  await separator.focus();
  await page.keyboard.press("Enter");
  await expect(separator).toHaveAttribute("aria-valuenow", "330");
  await expect
    .poll(async () => Math.round((await inspector.boundingBox())?.width ?? 0))
    .toBe(330);

  await separator.focus();
  await page.keyboard.press("ArrowLeft");
  await page.getByRole("button", { name: "Reset panel width" }).click();
  await expect(separator).toHaveAttribute("aria-valuenow", "330");
});

test("details panel resize control is hidden in stacked layouts", async ({ page }) => {
  await page.setViewportSize({ width: 1_101, height: 844 });
  await loadMap(page);
  const separator = page.getByRole("separator", { name: "Resize details panel" });
  await separator.focus();
  await page.setViewportSize({ width: 1_100, height: 844 });
  await expect(page.locator("#map-inspector")).toBeFocused();
  await expect(
    page.getByRole("separator", { name: "Resize details panel", includeHidden: true }),
  ).toBeHidden();

  await page.setViewportSize({ width: 1_101, height: 844 });
  await page.getByRole("button", { name: "Reset panel width" }).focus();
  await page.setViewportSize({ width: 1_100, height: 844 });
  await expect(page.locator("#map-inspector")).toBeFocused();
});

test("context loss falls back to 2D", async ({ page }) => {
  await loadMap(page);
  const graph3d = page.getByLabel("Interactive 3D research graph");
  if (await graph3d.count()) {
    await graph3d
      .locator("canvas:not(.cloud-plane)")
      .first()
      .dispatchEvent("webglcontextlost");
    await expect(page.getByLabel("Interactive research graph")).toContainText(
      "2D overview · semantic frame",
    );
    await expect(
      page.locator(".graph-status").filter({
        hasText: "3D stopped; using the 2D fallback.",
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Retry 3D" }).click();
    const rebuilt = page.getByLabel("Interactive 3D research graph");
    await expect(rebuilt.locator("canvas:not(.cloud-plane)")).toBeVisible();
    await rebuilt.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByLabel("Choose a visible graph node")).not.toHaveValue("");
    await expect(page.getByRole("button", { name: "Close inspector" })).toBeVisible();
  } else {
    await expect(
      page.locator(".graph-status").filter({
        hasText: "3D unavailable; using the 2D fallback.",
      }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Interactive research graph").locator("canvas:not(.cloud-plane)"),
    ).toBeVisible();
  }
});

test("320px map passes axe", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await loadMap(page);
  await scanAxe(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
});

test("200% map passes axe", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await loadMap(page);
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await scanAxe(page);
});
