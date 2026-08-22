import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { buildHarnessSubmenu, registerHarnessMenu } from "../dsh-plugin/lib/menu.js";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function label(item) { return item.label?.(); }

test("builds a Kimi-compatible native skin menu from shared HarnessUI state", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "dsh-harness-menu-"));
  fs.writeFileSync(path.join(root, "catalog.json"), JSON.stringify({
    count: 3,
    entries: [
      { id: "amber-default", game: "genshin", gameName: "原神", character: "amber", characterZh: "安柏", variant: "default", variantZh: "默认", fullLabel: "安柏·默认" },
      { id: "amber-summer", game: "genshin", gameName: "原神", character: "amber", characterZh: "安柏", variant: "summer", variantZh: "夏日", fullLabel: "安柏·夏日" },
      { id: "klee-default", game: "genshin", gameName: "原神", character: "klee", characterZh: "可莉", variant: "default", variantZh: "默认", fullLabel: "可莉·默认" },
    ],
  }));
  fs.writeFileSync(path.join(root, "state.json"), JSON.stringify({ mode: "gallery", selected: "amber-summer" }));
  fs.writeFileSync(path.join(root, "refresh-status.json"), JSON.stringify({ status: "partial", message: "SMB 缺少 2 项，本地完整库已保留" }));
  const requests = [];
  let libraryOpenCount = 0;
  const items = buildHarnessSubmenu({
    dataRoot: root,
    request: async (route, body) => { requests.push({ route, body }); },
    openLibrary: () => { libraryOpenCount += 1; },
  });
  assert.ok(items.some((item) => label(item) === "素材库：3 个变体"));
  assert.ok(items.some((item) => label(item) === "当前：安柏·夏日"));
  assert.ok(items.some((item) => label(item)?.startsWith("同步状态：SMB 缺少 2 项")));
  await items.find((item) => label(item) === "打开完整素材库").invoke();
  assert.equal(libraryOpenCount, 1);
  await items.find((item) => label(item)?.startsWith("换下一张")).invoke();
  assert.deepEqual(requests.pop(), { route: "/api/next", body: undefined });
  const game = items.find((item) => label(item) === "原神");
  const amber = game.submenu().find((item) => label(item) === "安柏");
  const summer = amber.submenu().find((item) => label(item) === "夏日");
  assert.equal(summer.type, "checkbox");
  assert.equal(summer.checked(), true);
  await summer.invoke();
  assert.deepEqual(requests.pop(), { route: "/api/state", body: { mode: "gallery", selected: "amber-summer" } });
  fs.rmSync(root, { recursive: true, force: true });
});

test("registers the DSH skin contribution as a separately promoted native menu", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "dsh-harness-register-"));
  let contributed;
  let disposed = false;
  const ctx = {
    desktopRuntime: {
      locale: "zh",
      registerTrayItem(item) {
        contributed = item;
        return { refresh() {}, dispose() { disposed = true; } };
      },
    },
  };
  const cleanup = registerHarnessMenu(ctx, { dataRoot: root, request: async () => {} });
  assert.equal(contributed.group, "harness");
  assert.equal(contributed.label(), "皮肤");
  assert.ok(Array.isArray(contributed.submenu()));
  cleanup();
  assert.equal(disposed, true);
  fs.rmSync(root, { recursive: true, force: true });
});

test("DSH overlay keeps semantic text and input surfaces readable in light and dark skins", () => {
  const client = fs.readFileSync(path.join(projectRoot, "dsh-plugin/lib/client.js"), "utf8");
  assert.match(client, /--dsw-alias-label-dimmed:#526174!important/);
  assert.match(client, /--dsw-alias-label-dimmed:#b6c0cf!important/);
  assert.match(client, /::placeholder\{color:#526174!important;opacity:1!important/);
  assert.match(client, /\[contenteditable="true"\]\)\{color:#172033!important;-webkit-text-fill-color:#172033!important/);
  assert.match(client, /\[contenteditable="true"\]\)\{color:#f4f7fb!important;-webkit-text-fill-color:#f4f7fb!important/);
  assert.match(client, /background-color:rgba\(248,250,255,\.96\)!important/);
  assert.match(client, /@media \(prefers-reduced-transparency:reduce\)/);
  assert.match(client, /let displayedScene = ""/);
  assert.match(client, /if \(!url \|\| url === displayedScene\) return;/);
});
