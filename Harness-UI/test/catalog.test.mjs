import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { assetPath, buildCatalog } from "../src/catalog.mjs";

const fixture = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "library");

test("builds the public catalog from the SMB directory contract", () => {
  const catalog = buildCatalog({ sourceRoot: fixture, clock: () => new Date("2026-08-21T00:00:00Z") });
  assert.equal(catalog.count, 1);
  assert.deepEqual(catalog.entries[0], {
    id: "genshin/aino/default",
    game: "genshin",
    gameName: "原神",
    character: "aino",
    variant: "default",
    characterZh: "爱诺",
    variantZh: "默认",
    label: "爱诺",
    fullLabel: "爱诺",
    light: "http://127.0.0.1:3099/assets/%E5%8E%9F%E7%A5%9E/aino/default/light?v=2026-08-21T00%3A00%3A00.000Z",
    dark: "http://127.0.0.1:3099/assets/%E5%8E%9F%E7%A5%9E/aino/default/dark?v=2026-08-21T00%3A00%3A00.000Z",
  });
});

test("maps asset URLs only into a known game skin directory", () => {
  assert.equal(assetPath(fixture, "/assets/%E5%8E%9F%E7%A5%9E/aino/default/light"),
    path.join(fixture, "原神", "aino", "skins", "default", "light.png"));
  assert.equal(assetPath(fixture, "/assets/%E5%8E%9F%E7%A5%9E/../default/light"), null);
  assert.equal(assetPath(fixture, "/assets/%E4%B8%8D%E5%AD%98%E5%9C%A8/aino/default/light"), null);
});
