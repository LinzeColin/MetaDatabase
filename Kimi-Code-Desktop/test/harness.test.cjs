const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const test = require("node:test");
const { assetWithRevision, assertLoopbackBase, catalogNeedsRefresh, selectHarnessEntry } = require("../src/runtime/harness.cjs");

test("only accepts a loopback Harness UI endpoint", () => {
  assert.equal(assertLoopbackBase("http://127.0.0.1:3099/path"), "http://127.0.0.1:3099");
  assert.throws(() => assertLoopbackBase("https://example.com"), /loopback/);
});

test("selects the persisted entry and falls back to the first entry", () => {
  const catalog = { entries: [{ id: "one" }, { id: "two" }] };
  assert.equal(selectHarnessEntry(catalog, { selected: "two" }).id, "two");
  assert.equal(selectHarnessEntry(catalog, { selected: "missing" }).id, "one");
});

test("uses a stable skin identity to avoid stale immutable image cache entries", () => {
  assert.equal(
    assetWithRevision("http://127.0.0.1:3099/assets/light", "generation", "hsr/guinaifen/default"),
    "http://127.0.0.1:3099/assets/light?v=generation&skin=hsr%2Fguinaifen%2Fdefault",
  );
  assert.equal(
    assetWithRevision("http://127.0.0.1:3099/assets/light?v=existing", "generation", "hsr/guinaifen/default"),
    "http://127.0.0.1:3099/assets/light?v=existing&skin=hsr%2Fguinaifen%2Fdefault",
  );
});

test("refreshes the Kimi skin menu when Harness UI publishes a new catalog generation", () => {
  assert.equal(catalogNeedsRefresh({ catalogGenerated: "two" }, { generated: "one" }), true);
  assert.equal(catalogNeedsRefresh({ catalogGenerated: "two" }, { generated: "two" }), false);
  assert.equal(catalogNeedsRefresh({}, { generated: "one" }), true);
});

test("stops polling and releases its window reference", () => {
  const { HarnessBridge } = require("../src/runtime/harness.cjs");
  const bridge = new HarnessBridge({ intervalMs: 60000 });
  bridge.refresh = async () => {};
  bridge.attach({ isDestroyed: () => false });
  assert.ok(bridge.timer);
  bridge.stop();
  assert.equal(bridge.timer, null);
  assert.equal(bridge.window, null);
});

test("uses the shared atomic next endpoint", async () => {
  let request = null;
  const server = http.createServer((incoming, response) => {
    let body = "";
    incoming.setEncoding("utf8");
    incoming.on("data", (chunk) => { body += chunk; });
    incoming.on("end", () => {
      request = { method: incoming.method, url: incoming.url, body };
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ selected: "two", updated: 42, catalogGenerated: "same" }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const { port } = server.address();
    const { HarnessBridge } = require("../src/runtime/harness.cjs");
    const bridge = new HarnessBridge({ baseUrl: `http://127.0.0.1:${port}` });
    bridge.catalog = { generated: "same", entries: [{ id: "two" }] };
    bridge.refresh = async ({ suppliedState }) => suppliedState;
    const state = await bridge.next();
    assert.deepEqual(request, { method: "POST", url: "/api/next", body: "{}" });
    assert.equal(state.selected, "two");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("waits for the SMB deployment receipt before refreshing the Kimi catalog", async () => {
  let refreshRequested = false;
  const server = http.createServer((incoming, response) => {
    response.setHeader("Content-Type", "application/json");
    if (incoming.method === "POST" && incoming.url === "/api/catalog/refresh") {
      refreshRequested = true;
      response.statusCode = 202;
      response.end('{"status":"accepted"}');
      return;
    }
    if (incoming.url === "/refresh-status.json") {
      response.end(JSON.stringify({ status: "partial", message: "SMB 缺少 1 个素材", updated: Date.now() + 1000 }));
      return;
    }
    if (incoming.url === "/state.json") {
      response.end('{"selected":"one","updated":42,"catalogGenerated":"new"}');
      return;
    }
    if (incoming.url === "/catalog.json") {
      response.end('{"generated":"new","count":1,"entries":[{"id":"one"}]}');
      return;
    }
    response.statusCode = 404;
    response.end("{}");
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const { port } = server.address();
    const { HarnessBridge } = require("../src/runtime/harness.cjs");
    const bridge = new HarnessBridge({ baseUrl: `http://127.0.0.1:${port}`, intervalMs: 10 });
    const status = await bridge.refreshCatalog();
    assert.equal(refreshRequested, true);
    assert.equal(status.status, "partial");
    assert.equal(bridge.catalog.generated, "new");
    assert.equal(bridge.state.selected, "one");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("restores the legacy next-skin keyboard shortcut", () => {
  const source = fs.readFileSync(path.join(__dirname, "../src/main.cjs"), "utf8");
  assert.match(source, /换下一张[^\n]+CmdOrCtrl\+Shift\+N[^\n]+harnessBridge\.next/);
});

test("reapplies the same skin after the renderer document reloads", async () => {
  const { HarnessBridge } = require("../src/runtime/harness.cjs");
  const scripts = [];
  const window = {
    isDestroyed: () => false,
    webContents: {
      executeJavaScript: async (source) => { scripts.push(source); return true; },
    },
  };
  const bridge = new HarnessBridge({ intervalMs: 60000 });
  bridge.window = window;
  bridge.catalog = {
    generated: "generation",
    entries: [{ id: "one", light: "/light", dark: "/dark" }],
  };
  bridge.state = { selected: "one", updated: 42 };

  await bridge.applyCurrent();
  await bridge.applyCurrent();
  bridge.state.updated = 43;
  await bridge.applyCurrent();
  assert.equal(scripts.length, 1);
  assert.equal(await bridge.reapply(window), true);
  assert.equal(scripts.length, 2);
  assert.match(scripts[1], /dataset\.harnessUi = "active"/);
});

test("renderer reload reinstalls CSS before reapplying the cached skin", () => {
  const source = fs.readFileSync(path.join(__dirname, "../src/main.cjs"), "utf8");
  assert.match(source, /did-finish-load[\s\S]+insertCSS\(harnessCss\)[\s\S]+harnessBridge\.reapply\(window\)/);
});

test("keeps themed application surfaces readable without hiding background artwork", () => {
  const css = fs.readFileSync(path.join(__dirname, "../src/harness.css"), "utf8");
  assert.doesNotMatch(css, /--color-bg:\s*transparent/);
  assert.doesNotMatch(css, /--color-sidebar-bg:\s*transparent/);
  assert.match(css, /#app \.app-shell\s*\{[\s\S]*?background-color:\s*transparent\s*!important/);
  assert.match(css, /#app \.main\s*\{[\s\S]*?background-color:\s*var\(--harness-main-wash\)\s*!important/);
  assert.match(css, /#app \.con\s*\{[\s\S]*?background-color:\s*var\(--harness-main-wash\)\s*!important/);
  assert.match(css, /#app \.content-wrap\s*\{[\s\S]*?background-color:\s*var\(--harness-reading-bg\)\s*!important/);
  assert.match(css, /--color-bg:\s*rgba\(250, 248, 250, \.64\)/);
  assert.match(css, /--color-sidebar-bg:\s*rgba\(250, 246, 250, \.74\)/);
  assert.match(css, /--harness-main-wash:\s*rgba\(250, 248, 250, \.10\)/);
  assert.match(css, /--harness-reading-bg:\s*rgba\(253, 251, 253, \.60\)/);
  assert.match(css, /--color-bg:\s*rgba\(18, 13, 21, \.68\)/);
  assert.match(css, /--color-sidebar-bg:\s*rgba\(30, 22, 34, \.76\)/);
  assert.match(css, /--harness-main-wash:\s*rgba\(18, 13, 21, \.14\)/);
  assert.match(css, /--harness-reading-bg:\s*rgba\(24, 18, 28, \.64\)/);
  assert.match(css, /\.content-wrap\s*\{[\s\S]*?backdrop-filter:\s*blur\(10px\)/);
  assert.match(css, /prefers-reduced-transparency:[\s\S]*?--harness-reading-bg:\s*#fdfbfd/);
  assert.match(css, /prefers-reduced-transparency:[\s\S]*?--harness-reading-bg:\s*#18121c/);
});

test("gives model and workspace popups an independent high-contrast surface", () => {
  const css = fs.readFileSync(path.join(__dirname, "../src/harness.css"), "utf8");
  assert.match(css, /\[role="dialog"\][\s\S]*?\[role="menu"\][\s\S]*?\.model-dropdown[\s\S]*?\.sa-menu[\s\S]*?\.ws-panel[\s\S]*?\.ui-dialog/);
  assert.match(css, /background-color:\s*var\(--harness-popup-bg\)\s*!important/);
  assert.match(css, /:is\(\.model-dropdown, \.sa-menu, \.ws-panel\)[\s\S]*?opacity:\s*1\s*!important/);
  assert.match(css, /--harness-popup-bg:\s*rgba\(253, 251, 253, \.99\)/);
  assert.match(css, /\.ui-dialog__overlay\s*\{/);
  assert.match(css, /-webkit-text-fill-color:\s*var\(--color-text\)/);
  assert.match(css, /--harness-popup-bg:\s*rgba\(24, 18, 28, \.99\)/);
  assert.match(css, /\[data-color-scheme="dark"\] :is\(#app, body\) :is\([\s\S]*?\[role="dialog"\][\s\S]*?background-color:\s*var\(--harness-popup-bg\)\s*!important/);
});
