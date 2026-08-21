import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("VPS3 ops routes use the shared bearer boundary and Node runtime", async () => {
  const routes = [
    "app/api/ops/status/route.ts",
    "app/api/ops/ovh/route.ts",
    "app/api/ops/pdb/route.ts",
  ];
  const sources = await Promise.all(routes.map((route) => readFile(route, "utf8")));
  for (const source of sources) {
    assert.ok(source.includes('export const runtime = "nodejs"'));
    assert.ok(source.includes("ensureOpsAuthorization(request)"));
    assert.ok(source.includes("NO_STORE_HEADERS"));
    assert.ok(source.includes("buildOpsProbePayload"));
  }
});

test("ops projection has a fixed public shape and never spreads arbitrary runtime data", async () => {
  const source = await readFile("server/security/ops.ts", "utf8");
  assert.ok(source.includes("type OpsProbeExtras"));
  assert.ok(source.includes("const capability = extras.readOnly"));
  assert.ok(source.includes("const writeMode = extras.writeMode"));
  assert.ok(source.includes("adapter: adapterName"));
  assert.ok(source.includes("reachable: true"));
  assert.ok(source.includes("timestamp: new Date().toISOString()"));
  assert.ok(source.includes("if (normalized === \"readonly\")"));
  assert.ok(source.includes("if (normalized === \"readwrite\")"));
  assert.equal(source.includes("...extras"), false);
});
