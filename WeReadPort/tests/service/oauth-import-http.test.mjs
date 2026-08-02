import test from "node:test";
import assert from "node:assert/strict";
import { createPlatformApp } from "../../service/platform/app.mjs";
import { PlatformService } from "../../service/platform/service.mjs";
import { testPlatform, requestContext, testConfig } from "./helpers.mjs";

const PASSWORD = "Correct-Horse-2026";
const WEREAD_KEY = `wrk-${"W".repeat(32)}`;

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

test("导入背压按账户持久执行，单一租户不能耗尽公共 worker", async t => {
  const platform = testPlatform({ config: testConfig({ maxActiveImportJobsPerAccount: 2 }) });
  t.after(platform.close);
  const first = await platform.service.registerPassword({ email: "queue-a@example.com", password: PASSWORD });
  const second = await platform.service.registerPassword({ email: "queue-b@example.com", password: PASSWORD });
  const selection = { items: [{ name: "书摘.md", path: "Vault/书摘.md", content: "账户级队列背压" }] };
  const firstJob = platform.service.createImportJob(first.account.id, "obsidian", selection, "queue-a-1");
  const secondJob = platform.service.createImportJob(first.account.id, "google", selection, "queue-a-2");
  assert.equal(platform.service.createImportJob(first.account.id, "obsidian", selection, "queue-a-1").id, firstJob.id, "幂等重试不应被配额误拒绝");
  assert.equal(secondJob.state, "PENDING");
  assert.throws(
    () => platform.service.createImportJob(first.account.id, "notion", selection, "queue-a-3"),
    error => error.code === "IMPORT_QUEUE_FULL" && error.status === 429,
  );
  assert.throws(
    () => platform.service.createWeReadSyncJob(first.account.id, { mode: "auto" }, "queue-a-weread"),
    error => error.code === "IMPORT_QUEUE_FULL" && error.status === 429,
  );
  assert.ok(platform.store.db.prepare("SELECT sql FROM sqlite_master WHERE type='index' AND name='import_jobs_active_account_idx'").get()?.sql, "活跃任务计数必须由账户级索引支持");
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const rejected = await app(new Request(`${platform.config.baseUrl}/v1/imports/obsidian/start`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin: platform.config.baseUrl,
      "sec-fetch-site": "same-origin",
      "x-wrp-internal-secret": platform.config.internalProxySecret,
      cookie: `wrp_session=${first.session.token}`,
      "x-csrf-token": first.session.csrf,
      "idempotency-key": "queue-a-http-rejected",
    },
    body: JSON.stringify({ selection }),
  }));
  assert.equal(rejected.status, 429);
  assert.deepEqual((await rejected.json()).error, { code: "IMPORT_QUEUE_FULL", message: "当前账户的导入任务已达上限，请等待现有任务完成后再试。" });
  assert.equal(platform.service.createImportJob(second.account.id, "obsidian", selection, "queue-b-1").state, "PENDING", "其他租户必须保有独立准入额度");
});

test("微信读书同步先建立可轮询后台任务，不占用账户平台代理响应窗口", async t => {
  const platform = testPlatform({ fetchImpl: async () => new Promise(() => {}) });
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: WEREAD_KEY, displayName: "后台同步用户" }, {}, { verify: false });
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const headers = {
    "content-type": "application/json",
    origin: platform.config.baseUrl,
    "sec-fetch-site": "same-origin",
    "x-wrp-internal-secret": platform.config.internalProxySecret,
    cookie: `wrp_session=${user.session.token}`,
    "x-csrf-token": user.session.csrf,
    "idempotency-key": "weread-sync-start-1",
  };
  const started = await app(new Request(`${platform.config.baseUrl}/v1/weread/sync`, { method: "POST", headers, body: JSON.stringify({ mode: "full", recommendationPages: 3 }) }));
  assert.equal(started.status, 202);
  const first = (await started.json()).job;
  assert.equal(first.provider, "weread");
  assert.equal(first.state, "PENDING");

  const repeated = await app(new Request(`${platform.config.baseUrl}/v1/weread/sync`, { method: "POST", headers: { ...headers, "idempotency-key": "weread-sync-start-2" }, body: JSON.stringify({ mode: "full", recommendationPages: 3 }) }));
  assert.equal(repeated.status, 202);
  assert.equal((await repeated.json()).job.id, first.id, "同一账户的在途同步不得重复排队");

  const status = await app(new Request(`${platform.config.baseUrl}/v1/weread/sync/jobs/${first.id}`, { headers }));
  assert.equal(status.status, 200);
  assert.equal((await status.json()).job.id, first.id);
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
  assert.equal(register.headers.get("cache-control"), "no-store");
  const payload = await register.json();
  const setCookie = register.headers.get("set-cookie");
  assert.doesNotMatch(setCookie, /;\s*Domain=/iu, "单一公开入口不得签发跨域 Cookie");
  const cookie = setCookie.split(";")[0];
  assert.ok(cookie.startsWith("wrp_session="));

  const rejected = await app(new Request(`${platform.config.baseUrl}/v1/notes`, { method: "POST", headers: { ...baseHeaders, cookie }, body: JSON.stringify({ title: "失败", content: "缺少 CSRF" }) }));
  assert.equal(rejected.status, 403);
  const saved = await app(new Request(`${platform.config.baseUrl}/v1/notes`, { method: "POST", headers: { ...baseHeaders, cookie, "x-csrf-token": payload.csrf }, body: JSON.stringify({ source: "manual", externalId: "http-one", title: "HTTP 笔记", content: "跨设备正文" }) }));
  assert.equal(saved.status, 201);
  const savedPayload = await saved.json();
  const filteredExport = await app(new Request(`${platform.config.baseUrl}/v1/notes/export`, { method: "POST", headers: { ...baseHeaders, cookie, "x-csrf-token": payload.csrf }, body: JSON.stringify({ ids: [savedPayload.note.id] }) }));
  assert.equal(filteredExport.status, 200);
  assert.equal((await filteredExport.json()).notes[0].content, "跨设备正文");
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
  const wereadExport = await app(new Request(`${platform.config.baseUrl}/v1/weread/export`, { headers: { ...baseHeaders, cookie: refreshedCookie } }));
  assert.equal(wereadExport.status, 200);
  assert.equal((await wereadExport.json()).source, "WeChat Reading");
});

test("对象存储短暂不可用或正文损坏时，笔记接口返回可恢复 503 且不泄露下游异常", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const user = await platform.service.registerPassword({ email: "object-health@example.com", password: PASSWORD });
  const note = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "object-health-note", title: "对象存储韧性", content: "恢复性错误必须对客户端安全。" });
  const headers = {
    origin: platform.config.baseUrl,
    "sec-fetch-site": "same-origin",
    "x-wrp-internal-secret": platform.config.internalProxySecret,
    cookie: `wrp_session=${user.session.token}`,
  };
  const originalGet = platform.objectStore.get.bind(platform.objectStore);
  platform.objectStore.get = async () => { throw new Error("simulated R2 read outage"); };
  const unavailable = await app(new Request(`${platform.config.baseUrl}/v1/notes/${note.id}`, { headers }));
  assert.equal(unavailable.status, 503);
  assert.deepEqual((await unavailable.json()).error, { code: "OBJECT_UNAVAILABLE", message: "笔记正文暂时不可用，请稍后重试。" });

  platform.objectStore.get = async () => ({ bytes: Buffer.from("not a valid encrypted note", "utf8"), metadata: {} });
  const corrupt = await app(new Request(`${platform.config.baseUrl}/v1/notes/${note.id}`, { headers }));
  assert.equal(corrupt.status, 503);
  const corruptPayload = await corrupt.json();
  assert.deepEqual(corruptPayload.error, { code: "OBJECT_CORRUPT", message: "笔记正文暂时不可用，请稍后重试。" });
  assert.equal(JSON.stringify(corruptPayload).includes("not a valid encrypted note"), false);
  platform.objectStore.get = originalGet;
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

test("账户恢复接口受会话、同源和 CSRF 保护，并且只能接受当前绑定密钥", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: WEREAD_KEY, displayName: "恢复 HTTP 用户" }, {}, { verify: false });
  platform.store.db.prepare("UPDATE credentials SET secret_encrypted=? WHERE account_id=? AND provider='weread'")
    .run("v1.invalid-envelope", user.account.id);
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const headers = {
    "content-type": "application/json",
    origin: platform.config.baseUrl,
    "sec-fetch-site": "same-origin",
    "x-wrp-internal-secret": platform.config.internalProxySecret,
    cookie: `wrp_session=${user.session.token}`,
  };
  const csrfRejected = await app(new Request(`${platform.config.baseUrl}/v1/account/recovery/weread`, { method: "POST", headers, body: JSON.stringify({ key: WEREAD_KEY }) }));
  assert.equal(csrfRejected.status, 403);
  const wrongKey = await app(new Request(`${platform.config.baseUrl}/v1/account/recovery/weread`, {
    method: "POST", headers: { ...headers, "x-csrf-token": user.session.csrf }, body: JSON.stringify({ key: `wrk-${"Q".repeat(32)}` }),
  }));
  assert.equal(wrongKey.status, 403);
  assert.deepEqual((await wrongKey.json()).error, { code: "RECOVERY_KEY_MISMATCH", message: "请使用当前账户已绑定的微信读书密钥完成恢复。" });
  const accepted = await app(new Request(`${platform.config.baseUrl}/v1/account/recovery/weread`, {
    method: "POST", headers: { ...headers, "x-csrf-token": user.session.csrf }, body: JSON.stringify({ key: WEREAD_KEY }),
  }));
  assert.equal(accepted.status, 200);
  const payload = await accepted.json();
  assert.equal(payload.account.id, user.account.id);
  assert.equal(payload.recovery.status, "QUEUED");
  assert.equal(JSON.stringify(payload).includes(WEREAD_KEY), false);
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
