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

function oauthCallbackRequest(headers = {}) {
  return new Request("https://weread.linzezhang.com/api/platform/v1/oauth/google/callback?state=test-state&code=test-code", {
    headers,
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
  assert.equal(captured.init.redirect, "manual", "服务端必须拒绝自动重定向，避免转发 Authorization");
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

test("账户 OAuth 回调只允许无 Origin 的跨站顶层导航", async () => {
  let forwarded;
  const env = {
    WEREAD_ACCOUNT_SERVICE_URL: "https://account.example.test",
    WRP_INTERNAL_PROXY_SECRET: "test-internal-proxy-secret-not-for-production",
    ACCOUNT_SERVICE_FETCH: async (_url, init) => {
      forwarded = init.headers;
      return Response.json({ error: { code: "OAUTH_STATE_INVALID" } }, { status: 400 });
    },
  };
  const allowed = await handleRequest(oauthCallbackRequest({
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
  }), env);
  assert.equal(allowed.status, 400, "有效回调导航必须到达账户服务，由 state/PKCE 决定成败");
  assert.equal(forwarded.get("sec-fetch-mode"), "navigate");
  assert.equal(forwarded.get("sec-fetch-dest"), "document");
  assert.equal(forwarded.get("x-wrp-public-origin"), "https://weread.linzezhang.com");

  const crossSiteFetch = await handleRequest(oauthCallbackRequest({ "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty" }), env);
  assert.equal(crossSiteFetch.status, 403);
  const forgedOrigin = await handleRequest(oauthCallbackRequest({ Origin: "https://attacker.invalid", "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document" }), env);
  assert.equal(forgedOrigin.status, 403);
});

test("账户代理向 OVH 传入 Worker 派生的公开 origin，而非客户端可伪造值", async () => {
  let forwarded;
  const response = await handleRequest(new Request("https://admin.weread.linzezhang.com/api/platform/v1/session", {
    headers: { Origin: "https://admin.weread.linzezhang.com", "Sec-Fetch-Site": "same-origin", "x-wrp-public-origin": "https://attacker.invalid" },
  }), {
    WRP_ADMIN_HOST: "admin.weread.linzezhang.com",
    WEREAD_ACCOUNT_SERVICE_URL: "https://account.example.test",
    WRP_INTERNAL_PROXY_SECRET: "test-internal-proxy-secret-not-for-production",
    ACCOUNT_SERVICE_FETCH: async (_url, init) => { forwarded = init.headers; return Response.json({ error: { code: "AUTH_REQUIRED" } }, { status: 401 }); },
  });
  assert.equal(response.status, 401);
  assert.equal(forwarded.get("x-wrp-public-origin"), "https://admin.weread.linzezhang.com");
});

test("账户代理逐条保留多 Set-Cookie 响应，不能合并或丢失迁移 Cookie", async () => {
  const headers = new Headers({ "Content-Type": "application/json" });
  headers.append("Set-Cookie", "wrp_session=current; Path=/; HttpOnly; SameSite=Lax; Secure");
  headers.append("Set-Cookie", "wrp_session=; Path=/; HttpOnly; SameSite=Lax; Domain=weread.linzezhang.com; Secure; Max-Age=0");
  const response = await handleRequest(new Request("https://weread.linzezhang.com/api/platform/v1/session", {
    headers: { Origin: "https://weread.linzezhang.com", "Sec-Fetch-Site": "same-origin" },
  }), {
    WEREAD_ACCOUNT_SERVICE_URL: "https://account.example.test",
    WRP_INTERNAL_PROXY_SECRET: "test-internal-proxy-secret-not-for-production",
    ACCOUNT_SERVICE_FETCH: async () => new Response(JSON.stringify({ account: {} }), { status: 200, headers }),
  });
  assert.equal(response.status, 200);
  assert.deepEqual(response.headers.getSetCookie(), [
    "wrp_session=current; Path=/; HttpOnly; SameSite=Lax; Secure",
    "wrp_session=; Path=/; HttpOnly; SameSite=Lax; Domain=weread.linzezhang.com; Secure; Max-Age=0",
  ]);
});

test("主站会话接力只允许跳转到受控管理员子域", async () => {
  const env = {
    WRP_ADMIN_HOST: "admin.weread.linzezhang.com",
    WEREAD_ACCOUNT_SERVICE_URL: "https://account.example.test",
    WRP_INTERNAL_PROXY_SECRET: "test-internal-proxy-secret-not-for-production",
    ACCOUNT_SERVICE_FETCH: async () => new Response(null, {
      status: 303,
      headers: {
        Location: "https://admin.weread.linzezhang.com/?handoff=1",
        "Set-Cookie": "wrp_session=test; Domain=weread.linzezhang.com; Path=/; HttpOnly",
      },
    }),
  };
  const allowed = await handleRequest(new Request("https://weread.linzezhang.com/api/platform/v1/session/handoff"), env);
  assert.equal(allowed.status, 303);
  assert.equal(allowed.headers.get("location"), "https://admin.weread.linzezhang.com/?handoff=1");
  assert.match(allowed.headers.get("set-cookie") || "", /Domain=weread\.linzezhang\.com/u);

  const blocked = await handleRequest(new Request("https://weread.linzezhang.com/api/platform/v1/session/handoff"), {
    ...env,
    ACCOUNT_SERVICE_FETCH: async () => new Response(null, { status: 303, headers: { Location: "https://attacker.invalid/" } }),
  });
  assert.equal(blocked.status, 502);
  assert.equal((await blocked.json()).error.code, "UPSTREAM_REDIRECT");
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
