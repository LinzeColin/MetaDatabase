import test from "node:test";
import assert from "node:assert/strict";
import { createGatewayClient, inspectBusinessResponse } from "../src/core/gateway.js";
import { OFFICIAL_WEREAD_GATEWAY, SOURCE_SKILL_VERSION } from "../src/core/constants.js";
import { userKey } from "./helpers.mjs";
import { gatewayCall } from "../service/platform/weread.mjs";

test("browser and account sync both satisfy the reviewed Tencent 1.0.5 gateway contract", async () => {
  const calls = [];
  const fetchImpl = async (_url, init) => {
    const body = JSON.parse(init.body);
    calls.push(body);
    if (body.skill_version !== "1.0.5") return Response.json({
      errcode: 0, upgrade_info: { message: "Upgrade the reviewed skill before continuing." },
    });
    return Response.json({ errcode: 0, books: [] });
  };
  const browser = createGatewayClient({ mode: "direct", fetchImpl, maxAttempts: 1 });
  await browser.call("/user/notebooks", { count: 100, lastSort: 1516907353 }, { key: userKey() });
  await gatewayCall(userKey(), "/user/notebooks", { count: 100, lastSort: 1516907353 }, { fetchImpl });
  assert.deepEqual(calls, Array.from({ length: 2 }, () => ({
    api_name: "/user/notebooks", skill_version: "1.0.5", count: 100, lastSort: 1516907353,
  })));
});

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

test("account gateway stops for top-level and wrapped upgrade instructions without exposing upstream text", async () => {
  for (const payload of [
    { errcode: 0, upgrade_info: { message: userKey() } },
    { errcode: 0, data: { upgrade_info: { message: userKey() } } },
  ]) {
    await assert.rejects(() => gatewayCall(userKey(), "/_list", {}, { fetchImpl: async () => Response.json(payload) }), error => {
      assert.equal(error.code, "UPGRADE_REQUIRED");
      assert.equal(JSON.stringify(error).includes(userKey()), false);
      return true;
    });
  }
});

test("account gateway preserves actionable auth and rate-limit codes for HTTP and business failures", async () => {
  for (const [status, errcode, expected] of [[401, 0, "AUTH"], [200, -2012, "AUTH"], [200, -2001, "AUTH"], [429, 0, "RATE_LIMIT"], [200, -429, "RATE_LIMIT"]]) {
    await assert.rejects(() => gatewayCall(userKey(), "/_list", {}, {
      fetchImpl: async () => Response.json({ errcode, errmsg: userKey() }, { status }),
    }), error => error.code === expected && !error.message.includes(userKey()));
  }
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

test("上游空正文或 HTML 403 不冒充密钥失效，也不重复请求", async () => {
  for (const body of ["", "<html>denied</html>"]) {
    let calls = 0;
    await assert.rejects(() => gatewayCall(userKey(), "/_list", {}, {
      fetchImpl: async () => { calls += 1; return new Response(body, { status: 403 }); },
    }), error => error.code === "UPSTREAM_DENIED" && error.status === 403);
    assert.equal(calls, 1);
  }
});

test("账户只读 gateway 对 499/-2014 等瞬时失败做有界重试，授权和升级不重试", async () => {
  for (const [status, errcode] of [[499, -2014], [503, 0], [429, -429]]) {
    let calls = 0;
    await gatewayCall(userKey(), "/_list", {}, { retryAttempts: 2, delay: async () => {}, fetchImpl: async () => {
      calls += 1;
      return calls === 1 ? Response.json({ errcode }, { status }) : Response.json({ errcode: 0 });
    } });
    assert.equal(calls, 2);
  }
  for (const payload of [{ errcode: -2012 }, { upgrade_info: { message: "升级" } }]) {
    let calls = 0;
    await assert.rejects(() => gatewayCall(userKey(), "/_list", {}, { retryAttempts: 3, delay: async () => {}, fetchImpl: async () => { calls += 1; return Response.json(payload); } }));
    assert.equal(calls, 1);
  }
  let calls = 0;
  await assert.rejects(() => gatewayCall(userKey(), "/_list", {}, { retryAttempts: 2, delay: async () => {}, fetchImpl: async () => { calls += 1; return Response.json({ errcode: -2014 }, { status: 499 }); } }));
  assert.equal(calls, 2);
});
