import test from "node:test";
import assert from "node:assert/strict";
import { createPlatformApp } from "../../service/platform/app.mjs";
import { testPlatform } from "./helpers.mjs";

const PASSWORD = "Correct-Horse-2026";
const ADMIN_ORIGIN = "https://admin.weread.linzezhang.com";

function configureAdmin(platform, accountId) {
  const config = Object.freeze({
    ...platform.config,
    adminBaseUrl: ADMIN_ORIGIN,
    allowedOrigins: Object.freeze([platform.config.baseUrl, ADMIN_ORIGIN]),
    adminAccountIds: Object.freeze([accountId]),
  });
  platform.service.config = config;
  return config;
}

function requestHeaders(platform, token, csrf = "", origin = platform.config.baseUrl, publicOrigin = origin) {
  const headers = {
    "x-wrp-internal-secret": platform.service.config.internalProxySecret,
    origin,
    "sec-fetch-site": "same-origin",
    cookie: `wrp_session=${token}`,
  };
  if (csrf) headers["x-csrf-token"] = csrf;
  if (publicOrigin) headers["x-wrp-public-origin"] = publicOrigin;
  return headers;
}

test("AI 偏好按账户密钥加密保存，单条问询记录不保存笔记正文", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const admin = await platform.service.registerPassword({ email: "admin@example.com", password: PASSWORD, displayName: "管理员" });
  const user = await platform.service.registerPassword({ email: "reader@example.com", password: PASSWORD, displayName: "阅读者" });
  configureAdmin(platform, admin.account.id);
  const note = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "ai-note", title: "单条笔记", content: "仅供我继续思考的笔记正文。", bookTitle: "思考练习", author: "作者甲" });

  const saved = platform.service.updateAiPreferences(user.account.id, {
    providerId: "kimi", styleId: "socratic", personalContext: "我在做长期决策。", customPrompt: "请优先追问反例。",
  });
  assert.equal(saved.providerId, "kimi");
  assert.equal(saved.styleId, "socratic");
  const encrypted = platform.store.getAiPreferences(user.account.id).preferencesEncrypted;
  assert.equal(encrypted.includes("长期决策"), false);
  assert.equal(encrypted.includes("优先追问"), false);
  assert.deepEqual(platform.service.getAiPreferences(user.account.id), saved);

  const event = platform.service.recordAiInquiry(user.account.id, { noteId: note.id, providerId: "kimi", styleId: "socratic" });
  const history = platform.service.listAiInquiryEvents(user.account.id);
  assert.equal(history[0].id, event.id);
  assert.equal(history[0].note.title, "单条笔记");
  const storedEvent = platform.store.db.prepare("SELECT provider_id AS providerId,style_id AS styleId,note_id AS noteId FROM ai_inquiry_events WHERE id=?").get(event.id);
  assert.equal(storedEvent.providerId, "kimi");
  assert.equal(storedEvent.styleId, "socratic");
  assert.equal(storedEvent.noteId, note.id);
});

test("管理员数据读取要求专用管理域、不可变账户白名单、近期验证和用途审计", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const admin = await platform.service.registerPassword({ email: "admin-http@example.com", password: PASSWORD, displayName: "管理员" });
  const user = await platform.service.registerPassword({ email: "reader-http@example.com", password: PASSWORD, displayName: "阅读者" });
  const config = configureAdmin(platform, admin.account.id);
  const note = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "admin-note", title: "管理员可审计读取", content: "正文只能在明确用途后读取。" });
  platform.service.updateAiPreferences(user.account.id, { providerId: "chatgpt", styleId: "blindspot", personalContext: "测试背景", customPrompt: "测试自定义提示词" });

  const adminSession = platform.service.authenticate(admin.session.token);
  const userSession = platform.service.authenticate(user.session.token);
  assert.throws(() => platform.service.adminAccounts(userSession, { reason: "处理测试用户请求" }), error => error?.code === "ADMIN_FORBIDDEN");
  assert.equal(platform.service.adminOverview(adminSession).counts.accounts, 2);
  const accounts = platform.service.adminAccounts(adminSession, { reason: "处理测试用户请求" }).accounts;
  assert.ok(accounts.some(item => item.id === user.account.id));
  const prompts = platform.service.adminPrompts(adminSession, { reason: "核验用户保存的问询偏好" }).preferences;
  assert.equal(prompts.find(item => item.accountId === user.account.id).preferences.customPrompt, "测试自定义提示词");
  const body = await platform.service.adminReadNote(adminSession, { noteId: note.id, reason: "响应用户笔记恢复工单" });
  assert.equal(body.note.content, "正文只能在明确用途后读取。");
  assert.ok(platform.service.adminAuditLog(adminSession, { reason: "复核近期管理操作" }).events.some(item => item.action === "admin_note_body_viewed"));

  const app = createPlatformApp({ service: platform.service, config });
  const accepted = await app(new Request(`${ADMIN_ORIGIN}/v1/admin/accounts`, {
    method: "POST",
    headers: { ...requestHeaders(platform, admin.session.token, admin.session.csrf, ADMIN_ORIGIN, ADMIN_ORIGIN), "content-type": "application/json" },
    body: JSON.stringify({ reason: "处理测试用户请求" }),
  }));
  assert.equal(accepted.status, 200);
  const rejected = await app(new Request(`${platform.config.baseUrl}/v1/admin/accounts`, {
    method: "POST",
    headers: { ...requestHeaders(platform, admin.session.token, admin.session.csrf, platform.config.baseUrl, platform.config.baseUrl), "content-type": "application/json" },
    body: JSON.stringify({ reason: "处理测试用户请求" }),
  }));
  assert.equal(rejected.status, 403);
});
