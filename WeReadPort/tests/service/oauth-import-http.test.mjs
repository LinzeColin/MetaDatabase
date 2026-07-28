import test from "node:test";
import assert from "node:assert/strict";
import { createPlatformApp } from "../../service/platform/app.mjs";
import { PlatformService } from "../../service/platform/service.mjs";
import { testPlatform, requestContext } from "./helpers.mjs";

const PASSWORD = "Correct-Horse-2026";

function oauthFetch(url, init = {}) {
  const target = String(url);
  if (target.includes("oauth2.googleapis.com/token")) {
    const code = new URLSearchParams(String(init.body || "")).get("code");
    const scope = code === "google-import" ? "openid email profile https://www.googleapis.com/auth/drive.readonly" : "openid email profile";
    return Promise.resolve(json({ access_token: "google-access", refresh_token: "google-refresh", expires_in: 3600, scope }));
  }
  if (target.includes("openidconnect.googleapis.com/v1/userinfo")) return Promise.resolve(json({ sub: "google-subject-1", email: "same@example.com", name: "Google 用户" }));
  if (target.includes("github.com/login/oauth/access_token")) return Promise.resolve(json({ access_token: "github-access", scope: "read:user,user:email" }));
  if (target === "https://api.github.com/user") return Promise.resolve(json({ id: 9001, email: "same@example.com", login: "same-user", name: "GitHub 用户" }));
  if (target.includes("www.googleapis.com/drive/v3/files/g1")) return Promise.resolve(new Response("Google 导入正文", { status: 200, headers: { "Content-Type": "text/plain" } }));
  if (target.includes("www.googleapis.com/drive/v3/files")) return Promise.resolve(json({ files: [{ id: "g1", name: "阅读笔记", mimeType: "text/plain", modifiedTime: "2026-07-28T00:00:00Z", size: "12" }] }));
  return Promise.resolve(json({ errcode: 0 }));
}
function json(value, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }); }
function stateFrom(result) { return new URL(result.authorizationUrl).searchParams.get("state"); }

test("Google 与 GitHub 同邮箱不会自动合并，只有显式绑定可进入同一账户", async t => {
  const platform = testPlatform({ fetchImpl: oauthFetch });
  t.after(platform.close);
  const googleStart = await platform.service.startOAuth("google", { intent: "login" });
  const google = await platform.service.completeOAuth("google", { state: stateFrom(googleStart), code: "google-code" }, requestContext());
  const githubStart = await platform.service.startOAuth("github", { intent: "login" });
  const github = await platform.service.completeOAuth("github", { state: stateFrom(githubStart), code: "github-code" }, requestContext());
  assert.notEqual(google.account.id, github.account.id, "相同邮箱不得隐式合并账户");

  const linkStart = await platform.service.startOAuth("github", { intent: "link", accountId: google.account.id });
  await assert.rejects(() => platform.service.completeOAuth("github", { state: stateFrom(linkStart), code: "github-code" }, {}, { expectedAccountId: google.account.id }), error => error.code === "CREDENTIAL_IN_USE");
});

test("Obsidian 新手导入任务幂等、可恢复并保存到账户", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerPassword({ email: "obsidian@example.com", password: PASSWORD, displayName: "导入用户" });
  const selection = { items: [{ name: "书摘.md", path: "Vault/书摘.md", content: "# 书摘\n\n一条笔记" }, { name: "想法.txt", path: "Vault/想法.txt", content: "我的想法" }] };
  const first = platform.service.createImportJob(user.account.id, "obsidian", selection, "same-operation");
  const duplicate = platform.service.createImportJob(user.account.id, "obsidian", selection, "same-operation");
  assert.equal(duplicate.id, first.id);
  const complete = await platform.service.processNextImportJob();
  assert.equal(complete.state, "COMPLETE");
  assert.equal(complete.progress.saved, 2);
  assert.equal(platform.service.listNotes(user.account.id).length, 2);
});

test("账户 HTTP 接口强制内部身份、同源、Cookie、CSRF 与账户会话", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const baseHeaders = { "content-type": "application/json", origin: platform.config.baseUrl, "sec-fetch-site": "same-origin", "x-wrp-internal-secret": platform.config.internalProxySecret };
  const missingInternal = await app(new Request(`${platform.config.baseUrl}/v1/auth/register/password`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: "http@example.com", password: PASSWORD }) }));
  assert.equal(missingInternal.status, 401);

  const register = await app(new Request(`${platform.config.baseUrl}/v1/auth/register/password`, { method: "POST", headers: baseHeaders, body: JSON.stringify({ email: "http@example.com", password: PASSWORD, displayName: "HTTP 用户" }) }));
  assert.equal(register.status, 200);
  const payload = await register.json();
  const cookie = register.headers.get("set-cookie").split(";")[0];
  assert.ok(cookie.startsWith("wrp_session="));

  const rejected = await app(new Request(`${platform.config.baseUrl}/v1/notes`, { method: "POST", headers: { ...baseHeaders, cookie }, body: JSON.stringify({ title: "失败", content: "缺少 CSRF" }) }));
  assert.equal(rejected.status, 403);
  const saved = await app(new Request(`${platform.config.baseUrl}/v1/notes`, { method: "POST", headers: { ...baseHeaders, cookie, "x-csrf-token": payload.csrf }, body: JSON.stringify({ source: "manual", externalId: "http-one", title: "HTTP 笔记", content: "跨设备正文" }) }));
  assert.equal(saved.status, 201);
  const session = await app(new Request(`${platform.config.baseUrl}/v1/session`, { headers: { ...baseHeaders, cookie } }));
  assert.equal(session.status, 200);
  const refreshedCookie = session.headers.get("set-cookie").split(";")[0];
  assert.equal((await session.json()).account.email, "http@example.com");
  const notReady = await app(new Request(`${platform.config.baseUrl}/readyz`));
  assert.equal(notReady.status, 503);
  platform.store.heartbeat("test-import-worker", "import", "v0.0.0.1.9");
  const ready = await app(new Request(`${platform.config.baseUrl}/readyz`));
  const readyPayload = await ready.json();
  assert.equal(ready.status, 200);
  assert.equal(readyPayload.ready, true);
  assert.equal(readyPayload.dependencies.database.ok, true);
  assert.equal(readyPayload.dependencies.objectStore.writeReadDelete, true);
  assert.equal(JSON.stringify(readyPayload).includes("accounts"), false);
  const lines = await app(new Request(`${platform.config.baseUrl}/v1/status/business-lines`, { headers: { ...baseHeaders, cookie: refreshedCookie } }));
  assert.equal((await lines.json()).lines.length, 11);
});

test("格式错误的微信读书密钥返回可恢复客户端错误", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const response = await app(new Request(`${platform.config.baseUrl}/v1/auth/login/weread`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin: platform.config.baseUrl,
      "sec-fetch-site": "same-origin",
      "x-wrp-internal-secret": platform.config.internalProxySecret,
    },
    body: JSON.stringify({ key: "not-a-real-weread-key" }),
  }));
  assert.equal(response.status, 400);
  assert.deepEqual((await response.json()).error, { code: "INVALID_KEY", message: "微信读书密钥格式无效。" });
});

test("OAuth 回调仅放行无 Origin 的跨站顶层导航", async t => {
  const platform = testPlatform({ fetchImpl: oauthFetch });
  t.after(platform.close);
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const start = await platform.service.startOAuth("google", { intent: "login" });
  const callbackHeaders = {
    "x-wrp-internal-secret": platform.config.internalProxySecret,
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
  };
  const accepted = await app(new Request(`${platform.config.baseUrl}/v1/oauth/google/callback?state=${encodeURIComponent(stateFrom(start))}&code=google-login`, { headers: callbackHeaders }));
  assert.equal(accepted.status, 303);
  assert.equal(new URL(accepted.headers.get("location")).origin, platform.config.baseUrl);

  const crossSiteFetch = await app(new Request(`${platform.config.baseUrl}/v1/oauth/google/callback?state=blocked&code=blocked`, {
    headers: { ...callbackHeaders, "sec-fetch-mode": "cors", "sec-fetch-dest": "empty" },
  }));
  assert.equal(crossSiteFetch.status, 403);
  const forgedOrigin = await app(new Request(`${platform.config.baseUrl}/v1/oauth/google/callback?state=blocked&code=blocked`, {
    headers: { ...callbackHeaders, origin: "https://attacker.invalid" },
  }));
  assert.equal(forgedOrigin.status, 403);
});

test("Google 登录与 Drive 导入权限分离，重新授权后才允许读取", async t => {
  const platform = testPlatform({ fetchImpl: oauthFetch });
  t.after(platform.close);
  const start = await platform.service.startOAuth("google", { intent: "login" });
  const user = await platform.service.completeOAuth("google", { state: stateFrom(start), code: "google-login" }, requestContext());
  assert.equal(user.account.connections.find(item => item.provider === "google").importReady, false);
  await assert.rejects(() => platform.service.listProviderItems(user.account.id, "google"), error => error.code === "PROVIDER_SCOPE_REQUIRED");

  const elevate = await platform.service.startOAuth("google", { intent: "import", accountId: user.account.id });
  await platform.service.completeOAuth("google", { state: stateFrom(elevate), code: "google-import" }, {}, { expectedAccountId: user.account.id });
  assert.equal(platform.service.publicAccount(user.account.id).connections.find(item => item.provider === "google").importReady, true);
  const items = await platform.service.listProviderItems(user.account.id, "google");
  assert.equal(items.items.length, 1);
  const job = platform.service.createImportJob(user.account.id, "google", { items: items.items }, "google-import-1");
  assert.equal(job.state, "PENDING");
  const complete = await platform.service.processNextImportJob();
  assert.equal(complete.state, "COMPLETE");
  const note = await platform.service.readNote(user.account.id, platform.service.listNotes(user.account.id)[0].id);
  assert.equal(note.content, "Google 导入正文");
});

test("OAuth 绑定、导入与重新验证必须回到发起授权的同一账户会话", async t => {
  const platform = testPlatform({ fetchImpl: oauthFetch });
  t.after(platform.close);
  const a = await platform.service.registerPassword({ email: "oauth-a@example.com", password: PASSWORD });
  const b = await platform.service.registerPassword({ email: "oauth-b@example.com", password: PASSWORD });
  const start = await platform.service.startOAuth("google", { intent: "link", accountId: a.account.id });
  await assert.rejects(
    () => platform.service.completeOAuth("google", { state: stateFrom(start), code: "google-login" }, {}, { expectedAccountId: b.account.id }),
    error => error.code === "OAUTH_SESSION_MISMATCH",
  );
});

test("OAuth 新账户持久化失败时回滚账户与凭据，不留下孤儿身份", async t => {
  const platform = testPlatform({ fetchImpl: oauthFetch });
  t.after(platform.close);
  const original = platform.store.upsertConnection.bind(platform.store);
  platform.store.upsertConnection = () => { throw Object.assign(new Error("simulated connection write failure"), { code: "WRITE_FAILED" }); };
  const start = await platform.service.startOAuth("google", { intent: "login" });
  await assert.rejects(() => platform.service.completeOAuth("google", { state: stateFrom(start), code: "google-login" }, requestContext()), error => error.code === "WRITE_FAILED");
  assert.equal(platform.store.db.prepare("SELECT COUNT(*) AS count FROM accounts").get().count, 0);
  assert.equal(platform.store.db.prepare("SELECT COUNT(*) AS count FROM credentials").get().count, 0);
  platform.store.upsertConnection = original;
});

test("就绪探针以数据库、对象存储、工作进程和三平台配置的真实状态裁决", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const first = await platform.service.readiness({ force: true });
  assert.equal(first.ready, false);
  assert.equal(first.dependencies.database.ok, true);
  assert.equal(first.dependencies.objectStore.ok, true);
  assert.equal(first.dependencies.importWorker.ok, false);
  platform.store.heartbeat("ready-worker", "import", "v0.0.0.1.9");
  const ready = await platform.service.readiness({ force: true });
  assert.equal(ready.ready, true);
  assert.ok(Object.values(ready.dependencies.providers).every(item => item.configured));

  const failingObjectStore = { ...platform.objectStore, healthCheck: async () => { throw new Error("object store unavailable"); } };
  const degraded = new PlatformService({ store: platform.store, objectStore: failingObjectStore, config: platform.config });
  const result = await degraded.readiness({ force: true });
  assert.equal(result.ready, false);
  assert.equal(result.dependencies.objectStore.code, "OBJECT_STORE_UNAVAILABLE");
});
