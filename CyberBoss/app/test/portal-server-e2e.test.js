"use strict";

// 设置页面真的被一台 HTTP 服务端出去了吗？
//
// 这套测试用真的 http 请求打真的服务器：拿页面、用一次性令牌换会话、带 CSRF
// 存密钥，最后确认存进去的密钥真能被聊天路径用上。域名校验按 Cloudflare
// Tunnel 的形态模拟——请求带着用户的域名作为 Host 和 Origin 到达本机回环口。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { UserAdmissionService } = require("../src/core/user-admission");
const { UserTurnRuntime } = require("../src/core/user-turn-runtime");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { SetupPortal } = require("../src/services/portal/setup-portal");
const { buildPortalHandlers } = require("../src/services/portal/portal-handlers");
const { PortalHttpServer } = require("../src/services/portal/portal-server");
const { OFFICIAL_ORIGINS } = require("../src/services/providers/router");

const ENCRYPTION_KEY = Buffer.alloc(32, 61);
const IDENTITY_KEY = Buffer.alloc(32, 67);
const BOT = "bot-server";
const ALICE = "alice-server";
const HOSTNAME = "boss.example.com";
const ORIGIN = `https://${HOSTNAME}`;

// 用裸 http 客户端而不是 fetch：fetch 不允许伪造 Host 头，而 Host 正是隧道
// 转发时带过来、服务端据以判断"这个请求确实是发给这个域名的"那个字段。裸客户端
// 发出的字节也更接近 cloudflared 真正发的东西。
function raw(port, { method = "GET", requestPath = "/", headers = {}, body = null } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === null ? null : Buffer.from(body);
    const request = http.request(
      {
        host: "127.0.0.1",
        port,
        method,
        path: requestPath,
        headers: {
          ...headers,
          ...(payload ? { "content-length": String(payload.length) } : {}),
        },
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let json = null;
          try {
            json = JSON.parse(text);
          } catch {
            json = null;
          }
          resolve({ status: response.statusCode, headers: response.headers, text, json });
        });
      },
    );
    request.on("error", reject);
    if (payload) {
      request.write(payload);
    }
    request.end();
  });
}

const POLICIES = Object.freeze({
  openai: { providerId: "openai", origin: OFFICIAL_ORIGINS.openai, models: ["gpt-5-mini"] },
  deepseek: { providerId: "deepseek", origin: OFFICIAL_ORIGINS.deepseek, models: ["deepseek-chat"] },
  google: { providerId: "google", origin: OFFICIAL_ORIGINS.google, models: ["gemini-2.5-flash"] },
  anthropic: { providerId: "anthropic", origin: OFFICIAL_ORIGINS.anthropic, models: ["claude-sonnet-5"] },
});

async function harness(t, { firstRun = false } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-httpd-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());

  const providerCalls = [];
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-server"],
    registrationMode: "invite",
    portalOrigin: ORIGIN,
  });
  const turnRuntime = new UserTurnRuntime({
    database: spool.database,
    userRepository: admission.users,
    encryptionKey: ENCRYPTION_KEY,
    providerPolicies: POLICIES,
    fetchImpl: async (url, init) => {
      providerCalls.push({
        url: String(url),
        authorization: init?.headers?.Authorization || init?.headers?.authorization || "",
      });
      return {
        ok: true,
        status: 200,
        async text() {
          return JSON.stringify({ output_text: "好的", usage: { input_tokens: 4, output_tokens: 2 } });
        },
      };
    },
  });
  const server = new PortalHttpServer({
    portal: new SetupPortal({
      database: spool.database,
      allowedOrigins: [ORIGIN],
      userRepository: admission.users,
      handlers: buildPortalHandlers({
        database: spool.database,
        vault: turnRuntime.vault,
        userRepository: admission.users,
        providerPolicies: POLICIES,
      }),
    }),
    // 端口 0：让内核挑一个空闲端口，测试之间不会互相抢。
    port: 0,
    usageProvider: () => 73,
    // 首次运行（还没有主人绑定）时后台数据接口免令牌；但 Owner 激活路由必须
    // 始终要令牌，这个测试就是来钉住这条区别的。
    firstRunProvider: () => firstRun,
    adminToken: "test-admin-token",
    ownerActivationStart: async () => ({ ok: true, qrcode: "x", content: "data:image/svg+xml;base64,AA==" }),
    ownerActivationPoll: async () => ({ ok: true, state: "wait" }),
    logger: { warn() {} },
  });
  const address = await server.start();
  t.after(() => server.stop());
  const base = `http://127.0.0.1:${address.port}`;

  const register = (senderRef) => {
    const invite = admission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
    admission.admit({ botAccountRef: BOT, senderRef, text: invite.code });
    admission.admit({ botAccountRef: BOT, senderRef, text: "同意并开始" });
    return admission.admit({ botAccountRef: BOT, senderRef, text: "hi" }).userContext;
  };

  // 隧道到达本机时的样子：Host 和 Origin 都是用户自己的域名。
  const tunnelHeaders = (extra = {}) => ({
    host: HOSTNAME,
    origin: ORIGIN,
    "content-type": "application/json",
    ...extra,
  });

  return { spool, admission, turnRuntime, server, address, base, register, tunnelHeaders, providerCalls };
}

test("GET /setup 端出真的页面，带 nonce 和用量，且不缓存", async (t) => {
  const h = await harness(t);

  const response = await raw(h.address.port, { requestPath: "/setup", headers: { host: HOSTNAME } });
  const html = response.text;

  assert.equal(response.status, 200);
  assert.match(response.headers["content-type"], /text\/html/);
  assert.equal(response.headers["cache-control"], "no-store");
  assert.equal(response.headers["x-content-type-options"], "nosniff");
  assert.equal(response.headers["referrer-policy"], "no-referrer");

  // 占位符必须已经被替换掉——留在页面里就说明渲染根本没跑。
  assert.equal(html.includes("__CSP_NONCE__"), false);
  assert.equal(html.includes("__USAGE_PERCENT__"), false);
  assert.match(html, />73</, "用量应该来自 usageProvider");

  // 每次请求一个新 nonce，而且 CSP 里和标签上是同一个。
  const nonce = html.match(/script nonce="([A-Za-z0-9_-]+)"/)[1];
  assert.equal(html.includes(`'nonce-${nonce}'`), true);
  const second = (await raw(h.address.port, { requestPath: "/setup", headers: { host: HOSTNAME } })).text;
  assert.notEqual(second.match(/script nonce="([A-Za-z0-9_-]+)"/)[1], nonce);

  // 页面上不能出现 inline style 属性，否则严格的 style-src nonce 就不够用了。
  assert.equal(/<[^>]+\sstyle=/.test(html), false);
});

test("一次性链接 → 换会话 → 存密钥 → 下一条微信消息真的用上了这把密钥", async (t) => {
  const h = await harness(t);
  const alice = h.register(ALICE);

  // 主人在微信里发「设置」拿到的那个链接，取出里面的令牌。
  const decision = h.admission.admit({ botAccountRef: BOT, senderRef: ALICE, text: "设置" });
  const url = new URL(decision.text.match(/https:\/\/\S+/)[0]);
  assert.equal(url.origin, ORIGIN);
  const params = new URLSearchParams(url.hash.slice(1));

  const exchange = await raw(h.address.port, {
    method: "POST",
    requestPath: "/api/session.exchange",
    headers: h.tunnelHeaders(),
    body: JSON.stringify({ token: params.get("t"), purpose: params.get("p") }),
  });
  const session = exchange.json;
  assert.equal(exchange.status, 200);
  assert.equal(session.ok, true);
  assert.ok(session.csrf);

  const cookie = [].concat(exchange.headers["set-cookie"])[0];
  assert.match(cookie, /HttpOnly/, "会话 cookie 必须是 HttpOnly，脚本读不到");
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Strict/);
  // 响应体里不能把 cookie 再抄一份出去。
  assert.equal(JSON.stringify(session).includes("HttpOnly"), false);

  const saved = await raw(h.address.port, {
    method: "POST",
    requestPath: "/api/provider.save",
    headers: h.tunnelHeaders({
      cookie: cookie.split(";")[0],
      "x-csrf-token": session.csrf,
    }),
    body: JSON.stringify({ provider_id: "openai", api_key: "sk-live-from-browser" }),
  });
  const savedBody = saved.json;
  assert.equal(saved.status, 200);
  assert.equal(savedBody.last4, "wser");
  assert.equal(JSON.stringify(savedBody).includes("sk-live-from-browser"), false, "密钥不能回显");

  // 真正的验收：网页上存的密钥，被微信那条路径用上了。
  const reply = await h.turnRuntime.handleTurn({
    userContext: alice,
    text: "在吗",
    requestId: "utr_via_browser",
  });
  assert.equal(reply.ok, true);
  assert.equal(h.providerCalls.length, 1);
  assert.match(h.providerCalls[0].url, /^https:\/\/api\.openai\.com\//);
  assert.match(h.providerCalls[0].authorization, /sk-live-from-browser$/);
});

test("换个域名来的请求一律拒绝，即使它直接打回环口", async (t) => {
  const h = await harness(t);

  // 直接用 127.0.0.1 作 Host 打进来——绕过隧道的那种打法。
  const direct = await raw(h.address.port, {
    method: "POST",
    requestPath: "/api/session.exchange",
    headers: { "content-type": "application/json", origin: ORIGIN, host: `127.0.0.1:${h.address.port}` },
    body: JSON.stringify({ token: "x".repeat(43), purpose: "provider" }),
  });
  assert.equal(direct.status, 403);
  assert.equal(direct.json.code, "HOST_NOT_ALLOWED");

  // 域名对但 Origin 是别人的。
  const wrongOrigin = await raw(h.address.port, {
    method: "POST",
    requestPath: "/api/session.exchange",
    headers: h.tunnelHeaders({ origin: "https://boss.example.com.evil.test" }),
    body: JSON.stringify({ token: "x".repeat(43), purpose: "provider" }),
  });
  assert.equal(wrongOrigin.status, 403);
  assert.equal(wrongOrigin.json.code, "ORIGIN_NOT_ALLOWED");
});

test("白名单以外的 action 和不存在的路径都不会走到任何处理函数", async (t) => {
  const h = await harness(t);

  const bogus = await raw(h.address.port, {
    method: "POST",
    requestPath: "/api/provider.stealAll",
    headers: h.tunnelHeaders(),
    body: "{}",
  });
  assert.equal(bogus.status, 403);
  assert.equal(bogus.json.code, "ACTION_NOT_ALLOWED");

  const missing = await raw(h.address.port, { requestPath: "/etc/passwd", headers: { host: HOSTNAME } });
  assert.equal(missing.status, 404);

  // GET 打 API 也不行：只有会改变状态的方法才被允许，而 GET 不在其中。
  const getApi = await raw(h.address.port, {
    requestPath: "/api/provider.save",
    headers: h.tunnelHeaders(),
  });
  assert.equal(getApi.status, 405);
});

test("超大 body 在被解析之前就被切断", async (t) => {
  const h = await harness(t);

  const response = await raw(h.address.port, {
    method: "POST",
    requestPath: "/api/provider.save",
    headers: h.tunnelHeaders(),
    body: "a".repeat(200 * 1024),
  });

  assert.equal(response.status, 413);
  assert.equal(response.json.code, "BODY_TOO_LARGE");
});

test("健康检查活着，但不透露任何状态", async (t) => {
  const h = await harness(t);
  const response = await raw(h.address.port, { requestPath: "/healthz", headers: { host: HOSTNAME } });
  assert.equal(response.status, 200);
  assert.equal(response.text, "ok");
});

test("只输域名（根路径）看到的是公开落地页，不是后台登录页", async (t) => {
  // 一开始这里走最后那个 404 分支，屏幕上只有 {"ok":false,"code":"NOT_FOUND"}
  // ——服务好好的，看起来却像彻底坏了。于是改成 302 跳 /admin。
  //
  // 但那一版对**陌生人**同样是死路：他打开这个域名，撞在主人的登录墙上，而
  // 「怎么开始用」没有任何入口。要做市场化的产品，大门不能开在员工通道上。
  // 现在给一页公开落地页：一个大按钮去 /join，底下一行小字给管理员。
  const h = await harness(t);
  for (const requestPath of ["/", "/index.html"]) {
    const response = await raw(h.address.port, { requestPath, headers: { host: HOSTNAME } });
    assert.equal(response.status, 200, `${requestPath} 应当直接给页面`);
    assert.match(response.text, /href="\/join"/, "落地页必须有去扫码页的入口");
    assert.match(response.text, /href="\/admin"/, "管理员也要进得去");
  }
});

test("R19 Owner 私有激活路由 /ops/wechat 存在，且数据接口要令牌", async (t) => {
  // 主人要扫的那一页。之前它是 404——overlay 里有实现，但从没接进跑着的程序，
  // 主人打开只会看到「找不到」。
  const h = await harness(t);
  const page = await raw(h.address.port, { requestPath: "/ops/wechat", headers: { host: HOSTNAME } });
  assert.equal(page.status, 200, "激活页必须能打开");
  assert.match(page.text, /授权微信/, "必须是中文的授权页");

  // 页面免令牌（页面本身不含凭据），数据接口必须要令牌。
  const start = await raw(h.address.port, {
    method: "POST", requestPath: "/ops/api/wechat/start", headers: { host: HOSTNAME },
  });
  assert.equal(start.status, 401, "没有令牌不得触发真实的微信授权请求");
});

test("Owner 激活路由不套用「首次运行免令牌」——那会让先到的人授权自己的微信", async (t) => {
  // 后台首次免令牌是安全的：那时库里没有任何数据。但这个路由能发起一次真实的
  // 微信授权，谁先扫谁的号就成了机器人。所以无论首次与否都必须要令牌。
  const h = await harness(t, { firstRun: true });
  for (const p of ["/ops/api/wechat/start", "/ops/api/wechat/poll?qrcode=x"]) {
    const res = await raw(h.address.port, { requestPath: p, headers: { host: HOSTNAME } });
    assert.equal(res.status, 401, `${p} 在首次运行时也必须要令牌`);
  }
});

test("公开入口与 Owner 激活是两个不同的 URL", async (t) => {
  // R19 明写这两个入口不得混淆：公开入口给普通用户扫，/ops/wechat 给主人扫。
  const h = await harness(t);
  const ops = await raw(h.address.port, { requestPath: "/ops/wechat", headers: { host: HOSTNAME } });
  const setup = await raw(h.address.port, { requestPath: "/setup", headers: { host: HOSTNAME } });
  assert.equal(ops.status, 200);
  assert.equal(setup.status, 200);
  assert.notEqual(ops.text, setup.text, "两个入口不得是同一个页面");
});
