import { readFileSync } from "node:fs";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";
import { limits, loadProfile, routeAssets } from "./budget.mjs";

function assertBudget(name, actual) {
  const limit = limits[name];
  assert.ok(
    actual.requests <= limit.requests,
    `${name} has ${actual.requests} asset requests; limit is ${limit.requests}`,
  );
  assert.ok(
    actual.raw <= limit.raw,
    `${name} is ${actual.raw} raw bytes; limit is ${limit.raw}`,
  );
  assert.ok(
    actual.gzip <= limit.gzip,
    `${name} is ${actual.gzip} gzip bytes; limit is ${limit.gzip}`,
  );
}

test("production chunks stay within route budgets", () => {
  const profile = loadProfile();
  for (const name of Object.keys(limits)) assertBudget(name, profile.sizes[name]);
});

test("2D and non-map routes cannot reach the 3D entry", () => {
  const profile = loadProfile();
  const { manifest, keys } = profile;
  const mapDynamic = manifest[keys.mapKey].dynamicImports ?? [];
  const relationKey = mapDynamic.find(
    (key) => manifest[key].src === "src/lib/relation.ts",
  );
  const rowKey = mapDynamic.find((key) => manifest[key].src === "src/lib/cloudrow.ts");
  assert.ok(relationKey);
  assert.ok(rowKey);
  assert.deepEqual(
    new Set(mapDynamic),
    new Set([keys.fallbackKey, keys.spaceKey, relationKey, rowKey]),
  );
  assert.equal(manifest[keys.fallbackKey].isDynamicEntry, true);
  assert.equal(manifest[keys.spaceKey].isDynamicEntry, true);
  assert.equal(manifest[relationKey].isDynamicEntry, true);
  assert.equal(manifest[rowKey].isDynamicEntry, true);

  const threeDEntry = manifest[keys.spaceKey].file;
  const forcedTwoD = routeAssets(profile, [
    keys.shellKey,
    keys.mapKey,
    keys.fallbackKey,
  ]);
  assert.equal(forcedTwoD.has(threeDEntry), false);
  assert.equal(forcedTwoD.has(manifest[relationKey].file), false);
  assert.equal(forcedTwoD.has(manifest[rowKey].file), false);

  for (const key of keys.nonMapKeys) {
    const assets = routeAssets(profile, [keys.shellKey, key]);
    assert.equal(assets.has(manifest[keys.mapKey].file), false);
    assert.equal(assets.has(manifest[keys.fallbackKey].file), false);
    assert.equal(assets.has(threeDEntry), false);
  }
});

test("initial route inventory contains core data before papers", () => {
  const profile = loadProfile();
  const core = JSON.parse(
    readFileSync(join(profile.root, "public/data/atlas.json"), "utf8"),
  );
  const initial = new Set([
    "index.html",
    ...routeAssets(profile, [profile.keys.shellKey, profile.keys.mapKey]),
    "data/atlas.json",
  ]);
  const json = [...initial].filter((file) => file.endsWith(".json"));
  assert.deepEqual(json, ["data/atlas.json"]);
  assert.equal(initial.has(core.paper_asset.path.replace(/^\//, "")), false);

  const eagerText = [...initial]
    .filter((file) => file === "index.html" || file.startsWith("assets/"))
    .map((file) => readFileSync(join(profile.root, "dist", file), "utf8"))
    .join("\n");
  assert.equal(eagerText.includes(core.paper_asset.path), false);
});
