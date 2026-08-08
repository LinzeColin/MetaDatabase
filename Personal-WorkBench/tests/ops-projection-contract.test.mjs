import assert from "node:assert/strict";
import test from "node:test";
import { GET as getStatus } from "../app/api/ops/status/route.ts";
import { GET as getOvh } from "../app/api/ops/ovh/route.ts";
import { GET as getPdb } from "../app/api/ops/pdb/route.ts";

function authHeader() {
  return `Bearer ${process.env.OPS_ADAPTER_TOKEN}`;
}

test("ops probes require adapter token and return probe payload", async () => {
  delete process.env.OPS_ADAPTER_TOKEN;
  const baseUrl = "https://example.com/api/ops/status";

  const statusWithoutToken = await getStatus(new Request(baseUrl));
  assert.equal(statusWithoutToken.status, 503);
  const statusBodyWithoutToken = await statusWithoutToken.json();
  assert.equal(statusBodyWithoutToken.message.includes("ops adapter secret"), true);

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
