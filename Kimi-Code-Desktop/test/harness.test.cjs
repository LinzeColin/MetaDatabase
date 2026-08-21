const assert = require("node:assert/strict");
const test = require("node:test");
const { assertLoopbackBase, catalogNeedsRefresh, selectHarnessEntry } = require("../src/runtime/harness.cjs");

test("only accepts a loopback Harness UI endpoint", () => {
  assert.equal(assertLoopbackBase("http://127.0.0.1:3099/path"), "http://127.0.0.1:3099");
  assert.throws(() => assertLoopbackBase("https://example.com"), /loopback/);
});

test("selects the persisted entry and falls back to the first entry", () => {
  const catalog = { entries: [{ id: "one" }, { id: "two" }] };
  assert.equal(selectHarnessEntry(catalog, { selected: "two" }).id, "two");
  assert.equal(selectHarnessEntry(catalog, { selected: "missing" }).id, "one");
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
