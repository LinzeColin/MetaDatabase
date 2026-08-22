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
  assert.equal(scripts.length, 1);
  assert.equal(await bridge.reapply(window), true);
  assert.equal(scripts.length, 2);
  assert.match(scripts[1], /dataset\.harnessUi = "active"/);
});

test("renderer reload reinstalls CSS before reapplying the cached skin", () => {
  const source = fs.readFileSync(path.join(__dirname, "../src/main.cjs"), "utf8");
  assert.match(source, /did-finish-load[\s\S]+insertCSS\(harnessCss\)[\s\S]+harnessBridge\.reapply\(window\)/);
});
