import test from "node:test";
import assert from "node:assert/strict";
import { handleRequest } from "../src/server/handler.js";
import { OFFICIAL_WEREAD_GATEWAY, SOURCE_SKILL_VERSION } from "../src/core/constants.js";
import { userKey } from "./helpers.mjs";

function gatewayRequest(body, headers = {}) {
  return new Request("https://status.linzezhang.com/api/weread/gateway", {
    method: "POST",
    headers: {
      Origin: "https://status.linzezhang.com",
      "Sec-Fetch-Site": "same-origin",
      "Content-Type": "application/json",
      Authorization: `Bearer ${userKey()}`,
      ...headers,
    },
    body: JSON.stringify(body),
  });
}

test("health and version routes are stateless", async () => {
  const health = await handleRequest(new Request("https://status.linzezhang.com/healthz"));
  assert.equal(health.status, 200);
  assert.equal((await health.json()).ok, true);
  const version = await handleRequest(new Request("https://status.linzezhang.com/api/version"));
  assert.equal((await version.json()).sourceSkillVersion, SOURCE_SKILL_VERSION);
});

test("proxy pins official endpoint and rebuilds the untrusted body", async () => {
  let captured;
  const response = await handleRequest(gatewayRequest({ api_name: "/book/info", bookId: "book-1", skill_version: "client-override" }), {
    UPSTREAM_FETCH: async (url, init) => {
      captured = { url, init };
      return Response.json({ errcode: 0, bookId: "book-1" });
    },
  });
  assert.equal(response.status, 200);
  assert.equal(captured.url, OFFICIAL_WEREAD_GATEWAY);
  assert.deepEqual(JSON.parse(captured.init.body), { api_name: "/book/info", skill_version: SOURCE_SKILL_VERSION, bookId: "book-1" });
  assert.equal(captured.init.headers.Authorization, `Bearer ${userKey()}`);
});

test("proxy rejects cross-origin and unknown parameters without leaking key", async () => {
  let called = false;
  const cross = await handleRequest(gatewayRequest({ api_name: "/_list" }, { Origin: "https://attacker.invalid", "Sec-Fetch-Site": "cross-site" }), { UPSTREAM_FETCH: async () => { called = true; return Response.json({}); } });
  assert.equal(cross.status, 403);
  assert.equal(called, false);
  const bad = await handleRequest(gatewayRequest({ api_name: "/book/info", bookId: "book-1", endpoint: "https://attacker.invalid" }), { UPSTREAM_FETCH: async () => Response.json({}) });
  const text = await bad.text();
  assert.equal(bad.status, 400);
  assert.ok(!text.includes(userKey()));
  assert.ok(!text.includes("attacker.invalid"));
});

test("proxy applies a bounded per-isolate rate limit", async () => {
  const env = { UPSTREAM_FETCH: async () => Response.json({ errcode: 0 }) };
  for (let index = 0; index < 240; index += 1) {
    const response = await handleRequest(gatewayRequest({ api_name: "/_list" }, { "CF-Connecting-IP": "203.0.113.10" }), env);
    assert.equal(response.status, 200);
  }
  const limited = await handleRequest(gatewayRequest({ api_name: "/_list" }, { "CF-Connecting-IP": "203.0.113.10" }), env);
  assert.equal(limited.status, 429);
});

test("proxy enforces a finite upstream timeout", async () => {
  const response = await handleRequest(gatewayRequest({ api_name: "/_list" }, { "CF-Connecting-IP": "203.0.113.77" }), {
    UPSTREAM_TIMEOUT_MS: 5,
    UPSTREAM_FETCH: async (_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(init.signal.reason), { once: true });
    }),
  });
  assert.equal(response.status, 504);
  const payload = await response.json();
  assert.equal(payload.error.code, "TIMEOUT");
});
