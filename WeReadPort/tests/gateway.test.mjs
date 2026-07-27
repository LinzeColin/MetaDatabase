import test from "node:test";
import assert from "node:assert/strict";
import { createGatewayClient, inspectBusinessResponse } from "../src/core/gateway.js";
import { OFFICIAL_WEREAD_GATEWAY, SOURCE_SKILL_VERSION } from "../src/core/constants.js";
import { userKey } from "./helpers.mjs";

test("direct gateway client pins endpoint, bearer key and source skill version", async () => {
  let captured;
  const client = createGatewayClient({
    mode: "direct",
    maxAttempts: 1,
    fetchImpl: async (url, init) => {
      captured = { url, init };
      return Response.json({ errcode: 0, data: { books: [] } });
    },
  });
  await client.call("/user/notebooks", { count: 100 }, { key: userKey() });
  assert.equal(captured.url, OFFICIAL_WEREAD_GATEWAY);
  assert.equal(captured.init.headers.Authorization, `Bearer ${userKey()}`);
  assert.deepEqual(JSON.parse(captured.init.body), { api_name: "/user/notebooks", skill_version: SOURCE_SKILL_VERSION, count: 100 });
});

test("upgrade instruction always fails closed", () => {
  assert.throws(() => inspectBusinessResponse({ errcode: 0, upgrade_info: { message: "upgrade now" } }), error => error.code === "BLOCKED_UPGRADE");
});

test("generic business error is not retried while transient HTTP is", async () => {
  let businessCalls = 0;
  const business = createGatewayClient({
    maxAttempts: 3,
    delay: async () => {},
    fetchImpl: async () => { businessCalls += 1; return Response.json({ errcode: 123, errmsg: "bad input" }); },
  });
  await assert.rejects(() => business.call("/user/notebooks", { count: 1 }, { key: userKey() }), error => error.code === "UPSTREAM");
  assert.equal(businessCalls, 1);

  let transientCalls = 0;
  const transient = createGatewayClient({
    maxAttempts: 2,
    delay: async () => {},
    fetchImpl: async () => { transientCalls += 1; return transientCalls === 1 ? Response.json({ error: "temporary" }, { status: 503 }) : Response.json({ errcode: 0, books: [] }); },
  });
  await transient.call("/user/notebooks", { count: 1 }, { key: userKey() });
  assert.equal(transientCalls, 2);
});
