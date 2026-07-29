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
    sessionCookieDomain: "weread.linzezhang.com",
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

test("管理员专用域直接展示数据，仍受不可变账户白名单和服务端记录约束", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const admin = await platform.service.registerPassword({ email: "admin-http@example.com", password: PASSWORD, displayName: "管理员" });
  const user = await platform.service.registerPassword({ email: "reader-http@example.com", password: PASSWORD, displayName: "阅读者" });
  const config = configureAdmin(platform, admin.account.id);
  const note = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "admin-note", title: "管理员可审计读取", content: "正文只能在明确用途后读取。" });
  await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "admin-skill-note", title: "系统框架", content: "用反馈回路框架检查长期后果。", bookTitle: "系统思维", author: "作者甲" });
  platform.service.updateAiPreferences(user.account.id, { providerId: "chatgpt", styleId: "blindspot", personalContext: "测试背景", customPrompt: "测试自定义提示词" });
  const savedSkill = await platform.service.saveBookSkill(user.account.id, { bookTitle: "系统思维", author: "作者甲" });

  const adminSession = platform.service.authenticate(admin.session.token);
  const userSession = platform.service.authenticate(user.session.token);
  assert.throws(() => platform.service.adminAccounts(userSession), error => error?.code === "ADMIN_FORBIDDEN");
  assert.equal(platform.service.adminOverview(adminSession).counts.accounts, 2);
  const accounts = platform.service.adminAccounts(adminSession).accounts;
  assert.ok(accounts.some(item => item.id === user.account.id));
  const prompts = platform.service.adminPrompts(adminSession).preferences;
  assert.equal(prompts.find(item => item.accountId === user.account.id).preferences.customPrompt, "测试自定义提示词");
  const body = await platform.service.adminReadNote(adminSession, { noteId: note.id });
  assert.equal(body.note.content, "正文只能在明确用途后读取。");
  const auditEvents = platform.service.adminAuditLog(adminSession).events;
  assert.ok(auditEvents.some(item => item.action === "admin_note_body_viewed"));
  assert.ok(auditEvents.some(item => item.action === "admin_note_body_viewed" && item.reason === "管理员直接查看"));
  const skills = platform.service.adminBookSkills(adminSession).bookSkills;
  assert.ok(skills.some(item => item.id === savedSkill.bookSkill.id));
  const skillBody = await platform.service.adminReadBookSkill(adminSession, { bookSkillId: savedSkill.bookSkill.id });
  assert.match(skillBody.artifact.markdown, /系统思维/u);
  const security = platform.service.adminSecurity(adminSession);
  assert.ok(security.securityEvents.some(item => item.accountId === user.account.id && item.eventType === "registration"));
  assert.ok(security.credentials.every(item => !Object.hasOwn(item, "subject")));
  assert.ok(security.sessions.every(item => !Object.hasOwn(item, "tokenHash")));

  platform.store.db.prepare("UPDATE sessions SET recent_auth_at=? WHERE token_hash=?")
    .run(platform.service.now() - 3_600, platform.service.sessionHash(admin.session.token));
  assert.doesNotThrow(() => platform.service.adminAccounts(platform.service.authenticate(admin.session.token)));

  const app = createPlatformApp({ service: platform.service, config });
  const accepted = await app(new Request(`${ADMIN_ORIGIN}/v1/admin/accounts`, {
    method: "POST",
    headers: { ...requestHeaders(platform, admin.session.token, admin.session.csrf, ADMIN_ORIGIN, ADMIN_ORIGIN), "content-type": "application/json" },
    body: JSON.stringify({}),
  }));
  assert.equal(accepted.status, 200);
  const rejected = await app(new Request(`${platform.config.baseUrl}/v1/admin/accounts`, {
    method: "POST",
    headers: { ...requestHeaders(platform, admin.session.token, admin.session.csrf, platform.config.baseUrl, platform.config.baseUrl), "content-type": "application/json" },
    body: JSON.stringify({}),
  }));
  assert.equal(rejected.status, 403);

  const handoff = await app(new Request(new URL("/v1/session/handoff", platform.config.baseUrl), {
    headers: requestHeaders(platform, admin.session.token, "", platform.config.baseUrl, platform.config.baseUrl),
  }));
  assert.equal(handoff.status, 303);
  assert.equal(handoff.headers.get("location"), ADMIN_ORIGIN + "/?handoff=1");
  assert.match(handoff.headers.get("set-cookie") || "", /Domain=weread\.linzezhang\.com/u);

  const nonAdminHandoff = await app(new Request(new URL("/v1/session/handoff", platform.config.baseUrl), {
    headers: requestHeaders(platform, user.session.token, "", platform.config.baseUrl, platform.config.baseUrl),
  }));
  assert.equal(nonAdminHandoff.status, 403);

  const sharedToken = /wrp_session=([^;]+)/u.exec(handoff.headers.get("set-cookie") || "")?.[1];
  assert.ok(sharedToken);
  const sharedSession = await app(new Request(new URL("/v1/session", ADMIN_ORIGIN), {
    headers: requestHeaders(platform, sharedToken, "", ADMIN_ORIGIN, ADMIN_ORIGIN),
  }));
  assert.equal(sharedSession.status, 200);
  assert.match(sharedSession.headers.get("set-cookie") || "", /Domain=weread\.linzezhang\.com/u);

  const renewedToken = /wrp_session=([^;]+)/u.exec(sharedSession.headers.get("set-cookie") || "")?.[1];
  assert.ok(renewedToken);
  const duplicateCookieSession = await app(new Request(new URL("/v1/session", ADMIN_ORIGIN), {
    headers: {
      ...requestHeaders(platform, renewedToken, "", ADMIN_ORIGIN, ADMIN_ORIGIN),
      cookie: "wrp_session=expired-host-only-cookie; wrp_session=" + renewedToken,
    },
  }));
  assert.equal(duplicateCookieSession.status, 200);
});
