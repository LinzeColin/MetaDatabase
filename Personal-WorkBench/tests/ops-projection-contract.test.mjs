import assert from "node:assert/strict";
import test from "node:test";
import { GET as getStatus } from "../app/api/ops/status/route.ts";
import { GET as getOvh } from "../app/api/ops/ovh/route.ts";
import { GET as getPdb } from "../app/api/ops/pdb/route.ts";
import {
  buildOpsProbePayload,
  normalizedOpsWriteMode,
} from "../server/security/ops.ts";

function authHeader() {
  return `Bearer ${process.env.OPS_ADAPTER_TOKEN}`;
}

test("ops probes require adapter token and return probe payload", async () => {
  delete process.env.OPS_ADAPTER_TOKEN;
  const baseUrl = "https://example.com/api/ops/status";

  const statusWithoutToken = await getStatus(new Request(baseUrl));
  assert.equal(statusWithoutToken.status, 503);
  const statusBodyWithoutToken = await statusWithoutToken.json();
  assert.equal(statusBodyWithoutToken.message, "ops adapter 暂不可用，请稍后重试。");
  assert.equal(statusBodyWithoutToken.message.includes("TOKEN"), false);

  process.env.OPS_ADAPTER_TOKEN = "unit-test-ops-token";
  const statusNoAuth = await getStatus(new Request(baseUrl));
  assert.equal(statusNoAuth.status, 401);

  const statusWithAuth = await getStatus(new Request(baseUrl, { headers: { authorization: authHeader() } }));
  assert.equal(statusWithAuth.status, 200);
  const statusPayload = await statusWithAuth.json();
  assert.equal(statusPayload.adapter, "status");
  assert.equal(statusPayload.reachable, true);

  const ovhPayload = await getOvh(new Request("https://example.com/api/ops/ovh", { headers: { authorization: authHeader() } }));
  assert.equal(ovhPayload.status, 200);
  const ovhBody = await ovhPayload.json();
  assert.equal(ovhBody.adapter, "ovh");
  assert.equal(typeof ovhBody.writeMode, "string");

  const pdbPayload = await getPdb(new Request("https://example.com/api/ops/pdb", { headers: { authorization: authHeader() } }));
  assert.equal(pdbPayload.status, 200);
  const pdbBody = await pdbPayload.json();
  assert.equal(pdbBody.adapter, "private_database");
});

test("ops projection allows only fixed low-sensitivity capability facts", () => {
  const payload = buildOpsProbePayload("status", {
    readOnly: true,
    // @ts-expect-error Contract test: untyped callers cannot inject fields.
    diary: "SENTINEL_DIARY_CONTENT",
    // @ts-expect-error Contract test: untyped callers cannot inject fields.
    token: "SENTINEL_OPS_TOKEN",
  });
  const serialized = JSON.stringify(payload);
  assert.equal(serialized.includes("SENTINEL_DIARY_CONTENT"), false);
  assert.equal(serialized.includes("SENTINEL_OPS_TOKEN"), false);
  assert.deepEqual(Object.keys(payload).sort(), ["adapter", "reachable", "readOnly", "timestamp"]);
  assert.equal(normalizedOpsWriteMode("READONLY"), "readonly");
  assert.equal(normalizedOpsWriteMode("readwrite"), "readwrite");
  assert.equal(normalizedOpsWriteMode("SENTINEL_PRIVATE_CONFIGURATION"), "unknown");
});

test("OVH and Private-Database probes never echo unrecognized runtime values", async () => {
  const previousOvh = process.env.OVH_ADAPTER_WRITE;
  const previousPdb = process.env.PRIVATE_DATABASE_ADAPTER_WRITE;
  process.env.OVH_ADAPTER_WRITE = "SENTINEL_OVH_CONFIGURATION";
  process.env.PRIVATE_DATABASE_ADAPTER_WRITE = "SENTINEL_PRIVATE_CONFIGURATION";
  try {
    const [ovh, pdb] = await Promise.all([
      getOvh(new Request("https://example.com/api/ops/ovh", { headers: { authorization: authHeader() } })),
      getPdb(new Request("https://example.com/api/ops/pdb", { headers: { authorization: authHeader() } })),
    ]);
    const [ovhBody, pdbBody] = await Promise.all([ovh.json(), pdb.json()]);
    assert.equal(ovhBody.writeMode, "unknown");
    assert.equal(pdbBody.writeMode, "unknown");
    assert.equal(JSON.stringify(ovhBody).includes("SENTINEL_OVH_CONFIGURATION"), false);
    assert.equal(JSON.stringify(pdbBody).includes("SENTINEL_PRIVATE_CONFIGURATION"), false);
  } finally {
    if (previousOvh === undefined) delete process.env.OVH_ADAPTER_WRITE;
    else process.env.OVH_ADAPTER_WRITE = previousOvh;
    if (previousPdb === undefined) delete process.env.PRIVATE_DATABASE_ADAPTER_WRITE;
    else process.env.PRIVATE_DATABASE_ADAPTER_WRITE = previousPdb;
  }
});
