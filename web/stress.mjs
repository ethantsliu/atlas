import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const COUNT = 3_100_000;
const POINT_BYTES = 13;
const LIMIT_BYTES = 39 * 1024 * 1024;
const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(ROOT, "dist");
const ZERO = "0".repeat(64);

function makeData() {
  const bytes = Buffer.allocUnsafe(12 + COUNT * POINT_BYTES);
  bytes.write("ATLASPT1", 0, "ascii");
  bytes.writeUInt32LE(COUNT, 8);
  const points = new Float32Array(bytes.buffer, bytes.byteOffset + 12, COUNT * 3);
  for (let index = 0; index < COUNT; index += 1) {
    const angle = index * 0.0001;
    points[index * 3] = Math.sin(angle) * 35;
    points[index * 3 + 1] = Math.cos(angle * 1.7) * 35;
    points[index * 3 + 2] = Math.sin(angle * 0.37) * 35;
  }
  bytes.fill(0, 12 + COUNT * 12);
  assert.equal(bytes.byteLength, 12 + COUNT * POINT_BYTES);
  assert.ok(bytes.byteLength <= LIMIT_BYTES, "Packed point cloud exceeds 39 MiB");
  return bytes;
}

function makeManifest(bytes) {
  const digest = createHash("sha256").update(bytes).digest("hex");
  const counts = { likely: COUNT, possible: 0, outside: 0 };
  const omitted = { likely: 0, possible: 0, outside: 0 };
  return {
    schema_version: 1,
    source: "arxiv",
    model: "all-minilm",
    model_digest: ZERO,
    model_revision: "0".repeat(40),
    projection: "anchor-cosine-8-v1",
    point_bytes: POINT_BYTES,
    source_count: COUNT,
    count: COUNT,
    counts,
    omitted_count: 0,
    omitted_counts: omitted,
    omitted_sha256: ZERO,
    foreground_sha256: ZERO,
    shards: [
      {
        month: "2026-08",
        source_sha256: ZERO,
        source_count: COUNT,
        source_counts: counts,
        foreground_sha256: ZERO,
        count: COUNT,
        counts,
        omitted_count: 0,
        omitted_counts: omitted,
        omitted_ids: [],
        omitted_sha256: ZERO,
        points: {
          path: "2026-08.bin",
          sha256: digest,
          bytes: bytes.byteLength,
        },
        meta: { path: "2026-08.json", sha256: ZERO, bytes: 1 },
      },
    ],
  };
}

function mime(path) {
  return (
    {
      ".css": "text/css",
      ".html": "text/html",
      ".js": "text/javascript",
      ".json": "application/json",
      ".woff2": "font/woff2",
    }[extname(path)] ?? "application/octet-stream"
  );
}

async function serve(bytes, manifest) {
  await stat(resolve(DIST, "index.html")).catch(() => {
    throw new Error("Build Atlas first with `npm run build`");
  });
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      if (url.pathname === "/data/cloud/index.json") {
        response.setHeader("content-type", "application/json");
        response.end(JSON.stringify(manifest));
        return;
      }
      if (url.pathname === "/data/cloud/2026-08.bin") {
        response.setHeader("content-type", "application/octet-stream");
        response.setHeader("content-length", String(bytes.byteLength));
        response.end(bytes);
        return;
      }
      const name = url.pathname === "/" ? "/index.html" : url.pathname;
      const path = resolve(DIST, `.${decodeURIComponent(name)}`);
      if (!path.startsWith(`${DIST}${sep}`)) {
        response.writeHead(403).end();
        return;
      }
      response.setHeader("content-type", mime(path));
      response.end(await readFile(path));
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  return {
    close: () => new Promise((done) => server.close(done)),
    url: `http://127.0.0.1:${address.port}`,
  };
}

function percentile(values, fraction) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * fraction))];
}

async function run(page, url, mode) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    globalThis.__atlasLong = [];
    new PerformanceObserver((list) => {
      globalThis.__atlasLong.push(
        ...list.getEntries().map((entry) => ({
          at: entry.startTime,
          ms: entry.duration,
        })),
      );
    }).observe({ type: "longtask", buffered: true });
  });
  const started = performance.now();
  await page.goto(`${url}/#?k=trpi&d=${mode === "3d" ? "3" : "2"}`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(
    (count) => {
      const text = document.querySelector(".graph-header")?.textContent ?? "";
      const match = text.match(/([\d,]+) nodes/);
      return match && Number(match[1].replaceAll(",", "")) >= count;
    },
    COUNT,
    { timeout: 60_000 },
  );
  const ready = performance.now() - started;
  await page.waitForFunction(
    () => {
      const entries = globalThis.__atlasLong;
      const last = entries.at(-1);
      const quiet = last ? performance.now() - last.at - last.ms : performance.now();
      return performance.now() > 2_000 && quiet > 750;
    },
    null,
    { timeout: 90_000 },
  );
  const settled = performance.now() - started;
  const before = await page.evaluate(() => globalThis.__atlasLong.length);
  const box = await page.locator(".graph-wrap").boundingBox();
  assert.ok(box);
  const hovered = performance.now();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(1_000);
  const hover = performance.now() - hovered;
  const result = await page.evaluate((offset) => {
    const entries = globalThis.__atlasLong;
    const context = document.createElement("canvas").getContext("webgl2");
    return {
      heap_bytes: performance.memory?.usedJSHeapSize ?? null,
      hover_tasks: entries.slice(offset),
      renderer: context?.getParameter(context.RENDERER) ?? null,
      tasks: entries,
      vendor: context?.getParameter(context.VENDOR) ?? null,
    };
  }, before);
  assert.deepEqual(errors, []);
  const durations = result.tasks.map((entry) => entry.ms);
  return {
    mode,
    ready_ms: Math.round(ready),
    settle_ms: Math.round(settled),
    hover_ms: Math.round(hover),
    heap_mib:
      result.heap_bytes == null
        ? null
        : Number((result.heap_bytes / 1024 / 1024).toFixed(1)),
    long_tasks: durations.length,
    long_p50_ms: Math.round(percentile(durations, 0.5)),
    long_p95_ms: Math.round(percentile(durations, 0.95)),
    long_max_ms: Math.round(Math.max(0, ...durations)),
    hover_max_ms: Math.round(
      Math.max(0, ...result.hover_tasks.map((entry) => entry.ms)),
    ),
    renderer: result.renderer,
    vendor: result.vendor,
  };
}

const bytes = makeData();
const manifest = makeManifest(bytes);
const host = await serve(bytes, manifest);
const browser = await chromium.launch({ headless: true });
try {
  const modes = [];
  for (const mode of ["2d", "3d"]) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    modes.push(await run(page, host.url, mode));
    await page.close();
  }
  console.log(
    JSON.stringify(
      {
        browser: await browser.version(),
        count: COUNT,
        packed_mib: Number((bytes.byteLength / 1024 / 1024).toFixed(2)),
        modes,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
  await host.close();
}
