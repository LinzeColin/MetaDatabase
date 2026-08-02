import test from "node:test";
import assert from "node:assert/strict";
import { testPlatform, requestContext, testConfig } from "./helpers.mjs";
import { PlatformService } from "../../service/platform/service.mjs";

const PASSWORD = "Correct-Horse-2026";
const KEY_ONE = `wrk-${"A".repeat(32)}`;
const KEY_TWO = `wrk-${"B".repeat(32)}`;

test("密码注册登录、密钥建账绑定和轮换都保持不可变 account_id", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const first = await platform.service.registerPassword({ email: "User@example.com", password: PASSWORD, displayName: "林知" }, requestContext());
  assert.match(first.account.id, /^acct_/);
  assert.equal(first.account.email, "user@example.com");
  assert.ok(!JSON.stringify(first.account).includes(PASSWORD));
  const login = await platform.service.loginPassword({ email: "user@example.com", password: PASSWORD }, requestContext());
  assert.equal(login.account.id, first.account.id);
  await assert.rejects(() => platform.service.loginPassword({ email: "user@example.com", password: "Wrong-Password-123" }), error => error.code === "INVALID_LOGIN");

  await platform.service.bindWeRead(first.account.id, KEY_ONE, { verify: false });
  const keyLogin = await platform.service.loginWeRead({ key: KEY_ONE }, requestContext());
  assert.equal(keyLogin.account.id, first.account.id);
  assert.equal(keyLogin.account.credentials.find(item => item.provider === "weread").label.endsWith("AAAA"), true);
  await platform.service.bindWeRead(first.account.id, KEY_TWO, { verify: false });
  assert.equal((await platform.service.loginWeRead({ key: KEY_TWO })).account.id, first.account.id);
  await assert.rejects(() => platform.service.loginWeRead({ key: KEY_ONE }), error => error.code === "INVALID_LOGIN");

  const keyOnly = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "密钥用户" }, requestContext(), { verify: false });
  assert.notEqual(keyOnly.account.id, first.account.id);
  await assert.rejects(() => platform.service.bindWeRead(keyOnly.account.id, KEY_TWO, { verify: false }), error => error.code === "CREDENTIAL_IN_USE");
});


test("密钥主体可以完成近期身份验证，敏感操作不强制依赖密码", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "密钥主体" }, requestContext(), { verify: false });
  const token = user.session.token;
  const hash = platform.service.sessionHash(token);
  platform.store.db.prepare("UPDATE sessions SET recent_auth_at=? WHERE token_hash=?").run(platform.store.now() - 3600, hash);
  assert.throws(() => platform.service.requireRecentAuth(platform.service.authenticate(token)), error => error.code === "RECENT_AUTH_REQUIRED");
  await platform.service.reauthenticateWeRead(user.account.id, KEY_ONE, token);
  assert.doesNotThrow(() => platform.service.requireRecentAuth(platform.service.authenticate(token)));
  await assert.rejects(() => platform.service.reauthenticateWeRead(user.account.id, KEY_TWO, token), error => error.code === "REAUTH_FAILED");
});

test("同一微信读书密钥登录会自愈不可解凭据，并由恢复任务强制完整重建", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "恢复用户" }, requestContext(), { verify: false });
  platform.store.db.prepare("UPDATE credentials SET secret_encrypted=? WHERE account_id=? AND provider='weread'")
    .run("v1.invalid-envelope", user.account.id);

  const login = await platform.service.loginWeRead({ key: KEY_ONE }, requestContext());
  assert.equal(login.account.id, user.account.id);
  assert.equal(login.recovery.status, "QUEUED");
  assert.equal(login.account.dataRecovery.status, "QUEUED");
  const queued = platform.store.findActiveImportJob(user.account.id, "weread");
  assert.ok(queued);
  assert.equal(JSON.stringify(queued).includes(KEY_ONE), false, "恢复任务不得保存原始密钥");

  let captured;
  platform.service.syncWeRead = async (accountId, input) => {
    captured = { accountId, input };
    return { summary: { syncMode: "full", importedDocuments: 0, updatedDocuments: 0, unchangedDocuments: 0, notebookBooks: 0, detailedBooks: 0, skippedUnchangedBooks: 0, coverage: { verified: true, unresolvedDocuments: 0 } }, capabilities: [], failures: [], coverage: { verified: true, unresolvedDocuments: 0 } };
  };
  const complete = await platform.service.processNextImportJob("recovery-worker");
  assert.equal(complete.state, "COMPLETE");
  assert.deepEqual(captured, { accountId: user.account.id, input: { mode: "full", recommendationPages: 3, recovery: true } });
  assert.equal(platform.service.publicAccount(user.account.id).dataRecovery.status, "HEALTHY");
  assert.equal(complete.progress.recovery.status, "HEALTHY");
});

test("恢复未取得来源覆盖证明时保持 PARTIAL，不把可读误报为完整恢复", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "部分恢复用户" }, requestContext(), { verify: false });
  platform.store.db.prepare("UPDATE credentials SET secret_encrypted=? WHERE account_id=? AND provider='weread'")
    .run("v1.invalid-envelope", user.account.id);
  await platform.service.loginWeRead({ key: KEY_ONE }, requestContext());
  platform.service.syncWeRead = async () => ({
    summary: { syncMode: "full", importedDocuments: 0, updatedDocuments: 0, unchangedDocuments: 0, notebookBooks: 0, detailedBooks: 0, skippedUnchangedBooks: 0, coverage: { verified: false, unresolvedDocuments: 1 } },
    capabilities: [], failures: [], coverage: { verified: false, unresolvedDocuments: 1 },
  });
  const complete = await platform.service.processNextImportJob("partial-recovery-worker");
  assert.equal(complete.state, "COMPLETE");
  assert.equal(complete.progress.recovery.status, "PARTIAL");
  assert.equal(platform.service.publicAccount(user.account.id).dataRecovery.status, "PARTIAL");
});

test("已运行的普通同步不会被误标为恢复任务，避免跳过后续完整重建", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "运行中恢复用户" }, requestContext(), { verify: false });
  const job = platform.service.createWeReadSyncJob(user.account.id, { mode: "auto" }, "running-normal-sync");
  assert.equal(platform.store.claimNextImportJob("already-running-worker", 300)?.id, job.id);
  platform.store.db.prepare("UPDATE credentials SET secret_encrypted=? WHERE account_id=? AND provider='weread'")
    .run("v1.invalid-envelope", user.account.id);

  const login = await platform.service.loginWeRead({ key: KEY_ONE }, requestContext());
  assert.equal(login.recovery.status, "REQUIRED");
  assert.equal(platform.store.findActiveImportJob(user.account.id, "weread")?.state, "RUNNING");
});

test("运行中普通同步结束后会补排受控恢复任务", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "后续恢复用户" }, requestContext(), { verify: false });
  const job = platform.service.createWeReadSyncJob(user.account.id, { mode: "auto" }, "normal-before-recovery");
  platform.store.db.prepare("UPDATE credentials SET secret_encrypted=? WHERE account_id=? AND provider='weread'")
    .run("v1.invalid-envelope", user.account.id);
  platform.service.syncWeRead = async () => {
    const login = await platform.service.loginWeRead({ key: KEY_ONE }, requestContext());
    assert.equal(login.recovery.status, "REQUIRED");
    return { summary: { syncMode: "incremental", importedDocuments: 0, updatedDocuments: 0, unchangedDocuments: 0, notebookBooks: 0, detailedBooks: 0, skippedUnchangedBooks: 0, coverage: { verified: true, unresolvedDocuments: 0 } }, capabilities: [], failures: [], coverage: { verified: true, unresolvedDocuments: 0 } };
  };
  const complete = await platform.service.processNextImportJob("normal-then-recovery-worker");
  assert.equal(complete.id, job.id);
  assert.equal(complete.state, "COMPLETE");
  assert.equal(platform.service.publicAccount(user.account.id).dataRecovery.status, "QUEUED");
  assert.equal(platform.store.findActiveImportJob(user.account.id, "weread")?.state, "PENDING");
});

test("微信读书账户的损坏正文进入受控恢复状态，而不是伪装成通用服务器错误", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "正文恢复用户" }, requestContext(), { verify: false });
  const note = await platform.service.saveDocument(user.account.id, { source: "weread", externalId: "recovery-note", title: "待恢复正文", content: "不会泄漏的测试正文" });
  const stored = platform.objectStore.objects.get(note.objectKey);
  platform.objectStore.objects.set(note.objectKey, { ...stored, bytes: Buffer.from("invalid-envelope", "utf8") });

  await assert.rejects(
    () => platform.service.readNote(user.account.id, note.id),
    error => error.code === "ACCOUNT_DATA_RECOVERY_REQUIRED" && error.status === 503,
  );
  const recovery = platform.service.publicAccount(user.account.id).dataRecovery;
  assert.equal(recovery.status, "REQUIRED");
  assert.equal(JSON.stringify(recovery).includes("invalid-envelope"), false);
});

test("强制重写与写后回读校验阻止新的损坏对象进入笔记索引", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerPassword({ email: "write-verify@example.com", password: PASSWORD });
  const first = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "rewrite-note", title: "第一版", content: "可验证正文" });
  const rewritten = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "rewrite-note", title: "第一版", content: "可验证正文" }, { forceRewrite: true, reportStatus: true });
  assert.equal(rewritten.unchanged, false);
  assert.equal(rewritten.note.version, first.version + 1);
  assert.equal((await platform.service.readNote(user.account.id, first.id)).content, "可验证正文");

  const originalGet = platform.objectStore.get.bind(platform.objectStore);
  platform.objectStore.get = async () => null;
  await assert.rejects(
    () => platform.service.saveDocument(user.account.id, { source: "manual", externalId: "write-verify-fail", title: "拒绝索引", content: "写后校验失败不得进入索引" }),
    error => error.code === "OBJECT_WRITE_VERIFY_FAILED" && error.status === 503,
  );
  platform.objectStore.get = originalGet;
  assert.equal(platform.store.findNote(user.account.id, "manual", "write-verify-fail"), null);
});

test("个人笔记按账户加密存储、跨租户不可读、版本冲突不静默覆盖", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const a = await platform.service.registerPassword({ email: "a@example.com", password: PASSWORD, displayName: "A" });
  const b = await platform.service.registerPassword({ email: "b@example.com", password: PASSWORD, displayName: "B" });
  const saved = await platform.service.saveDocument(a.account.id, { source: "manual", externalId: "shared-id", title: "只属于 A", content: "A 的私人笔记正文" });
  assert.equal(saved.version, 1);
  assert.equal(await platform.service.readNote(b.account.id, saved.id), null);
  const object = [...platform.objectStore.objects.values()][0];
  assert.ok(object);
  assert.ok(!object.bytes.toString("utf8").includes("私人笔记正文"));
  assert.equal((await platform.service.readNote(a.account.id, saved.id)).content, "A 的私人笔记正文");

  const updated = await platform.service.saveDocument(a.account.id, { source: "manual", externalId: "shared-id", title: "第二版", content: "第二版正文" }, { expectedVersion: 1 });
  assert.equal(updated.version, 2);
  const conflict = await platform.service.saveDocument(a.account.id, { source: "manual", externalId: "shared-id", title: "过期设备", content: "不应覆盖" }, { expectedVersion: 1 });
  assert.equal(conflict.conflict, true);
  assert.equal((await platform.service.readNote(a.account.id, saved.id)).content, "第二版正文");

  const pull = await platform.service.syncPull(a.account.id, 0, 50);
  assert.ok(pull.events.length >= 2);
  assert.ok(pull.events.every(event => event.note?.accountId === a.account.id));
  const otherPull = await platform.service.syncPull(b.account.id, 0, 50);
  assert.equal(otherPull.events.length, 0);
});

test("行为分析需明确同意，撤销后删除非必要事件且推荐不依赖模型 Token", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerPassword({ email: "consent@example.com", password: PASSWORD, displayName: "同意测试" });
  await platform.service.saveDocument(user.account.id, { source: "obsidian", externalId: "one", title: "工程", content: "系统设计与数据治理", category: "工程" });
  assert.equal(platform.store.listBehaviorEvents(user.account.id).length, 0);
  platform.service.updateConsent(user.account.id, { behaviorAnalytics: true, recommendationPersonalization: true });
  platform.service.audit(user.account.id, "reading_session", { minutes: 30, content: "不得进入事件" });
  assert.equal(platform.store.listBehaviorEvents(user.account.id).length, 1);
  const dashboard = platform.service.analytics(user.account.id);
  assert.equal(dashboard.privacy.modelOrTokenDependency, 0);
  assert.equal(dashboard.privacy.rawNoteTextUsedInBehaviorEvents, false);
  assert.ok(dashboard.recommendations.length >= 1);
  platform.service.updateConsent(user.account.id, { behaviorAnalytics: false, recommendationPersonalization: false });
  assert.equal(platform.store.listBehaviorEvents(user.account.id).length, 0);
  assert.equal(platform.service.analytics(user.account.id).recommendations.length, 0);
});


test("账户导出包含本人内容但不泄漏密码摘要、密钥、OAuth Token 或 R2 对象键", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const rawPassword = "Export-Secret-Password-2026";
  const rawWeReadKey = `wrk-${"X".repeat(32)}`;
  const user = await platform.service.registerPassword({ email: "export@example.com", password: rawPassword, displayName: "导出用户" });
  await platform.service.bindWeRead(user.account.id, rawWeReadKey, { verify: false });
  platform.store.upsertConnection({
    id: "conn_export_test",
    accountId: user.account.id,
    provider: "google",
    providerSubject: "google-export-subject",
    accessTokenEncrypted: "ciphertext-access-token-do-not-export",
    refreshTokenEncrypted: "ciphertext-refresh-token-do-not-export",
    scopes: "openid drive.readonly",
    expiresAt: null,
    metadata: { displayName: "导出测试", emailHint: "e***@example.com" },
  });
  await platform.service.saveDocument(user.account.id, {
    source: "manual", externalId: "export-note", title: "我的导出笔记", content: "这是账户持有者有权导出的正文。",
  });
  await platform.service.saveDocument(user.account.id, {
    source: "weread", externalId: "highlight:export-note", title: "微信读书导出笔记", content: "这是微信读书同步的正文。", bookTitle: "导出测试书", author: "测试作者", chapterTitle: "第一章", noteKind: "highlight", eventAt: 1_780_000_000,
  });
  const exported = await platform.service.exportAccount(user.account.id);
  const serialized = JSON.stringify(exported);
  assert.match(serialized, /账户持有者有权导出的正文/u);
  for (const forbidden of [
    rawPassword, rawWeReadKey, "ciphertext-access-token-do-not-export", "ciphertext-refresh-token-do-not-export",
    "secretHash", "secretEncrypted", "accessTokenEncrypted", "refreshTokenEncrypted", "objectKey", "wrappedDek",
  ]) assert.equal(serialized.includes(forbidden), false, `导出中不得出现：${forbidden}`);
  assert.ok(exported.credentials.every(item => !String(item.subject || "").includes("export@example.com")));
  const wereadExport = await platform.service.exportWeRead(user.account.id);
  assert.equal(wereadExport.source, "WeChat Reading");
  assert.equal(wereadExport.notes.length, 1);
  assert.equal(wereadExport.notes[0].source, "weread");
  assert.deepEqual({ bookTitle: wereadExport.notes[0].bookTitle, author: wereadExport.notes[0].author, chapterTitle: wereadExport.notes[0].chapterTitle, noteKind: wereadExport.notes[0].noteKind }, { bookTitle: "导出测试书", author: "测试作者", chapterTitle: "第一章", noteKind: "highlight" });
  const filtered = await platform.service.exportNotes(user.account.id, [wereadExport.notes[0].id]);
  assert.equal(filtered.scope, "filtered-notes");
  assert.equal(filtered.notes.length, 1);
  assert.equal(filtered.notes[0].content, "这是微信读书同步的正文。");
  assert.equal(JSON.stringify(wereadExport).includes("ciphertext-access-token-do-not-export"), false);
});

test("密钥主体可一键补设邮箱密码，并可查看和撤销跨设备会话", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const keyUser = await platform.service.registerWeRead({ key: KEY_ONE, displayName: "密钥主体" }, requestContext(), { verify: false });
  const configured = await platform.service.configurePassword(keyUser.account.id, {
    email: "key-owner@example.com",
    newPassword: PASSWORD,
  }, keyUser.session.token);
  assert.equal(configured.account.id, keyUser.account.id);
  assert.equal(configured.account.email, "key-owner@example.com");
  assert.ok(configured.account.credentials.some(item => item.provider === "email"));

  const secondDevice = await platform.service.loginPassword({ email: "key-owner@example.com", password: PASSWORD }, { userAgent: "second-device", ipPrefix: "198.51.100.0/24" });
  assert.equal(secondDevice.account.id, keyUser.account.id);
  const sessions = platform.service.listSessions(keyUser.account.id, keyUser.session.token);
  assert.equal(sessions.length, 2);
  assert.equal(sessions.filter(item => item.current).length, 1);
  assert.ok(sessions.every(item => !Object.hasOwn(item, "tokenHash")));

  const revoked = platform.service.revokeOtherSessions(keyUser.account.id, keyUser.session.token);
  assert.equal(revoked.revoked, 1);
  assert.equal(platform.service.authenticate(secondDevice.session.token), null);

  await platform.service.configurePassword(keyUser.account.id, {
    email: "key-owner@example.com",
    currentPassword: PASSWORD,
    newPassword: "New-Secure-Password-2026",
  }, keyUser.session.token);
  await assert.rejects(() => platform.service.loginPassword({ email: "key-owner@example.com", password: PASSWORD }), error => error.code === "INVALID_LOGIN");
  const changed = await platform.service.loginPassword({ email: "key-owner@example.com", password: "New-Secure-Password-2026" });
  assert.equal(changed.account.id, keyUser.account.id);
});

test("登录失败计数持久化到 SQLite，服务重启不会清空暴力破解锁", async t => {
  let now = Date.now();
  const clock = () => now;
  const platform = testPlatform({ clock, config: testConfig({ authFailureLimit: 3, authLockSeconds: 120, authFailureWindowSeconds: 600 }) });
  t.after(platform.close);
  await platform.service.registerPassword({ email: "rate@example.com", password: PASSWORD });
  await assert.rejects(() => platform.service.loginPassword({ email: "rate@example.com", password: "Wrong-Password-1" }, requestContext()), error => error.code === "INVALID_LOGIN");
  await assert.rejects(() => platform.service.loginPassword({ email: "rate@example.com", password: "Wrong-Password-2" }, requestContext()), error => error.code === "INVALID_LOGIN");
  await assert.rejects(() => platform.service.loginPassword({ email: "rate@example.com", password: "Wrong-Password-3" }, requestContext()), error => error.code === "RATE_LIMIT");

  const restarted = new PlatformService({ store: platform.store, objectStore: platform.objectStore, config: platform.config, clock });
  await assert.rejects(() => restarted.loginPassword({ email: "rate@example.com", password: PASSWORD }, requestContext()), error => error.code === "RATE_LIMIT");
  now += 121_000;
  const login = await restarted.loginPassword({ email: "rate@example.com", password: PASSWORD }, requestContext());
  assert.equal(login.account.email, "rate@example.com");
});

test("导入暂存内容只以账户密钥加密，任务接口和 SQLite 明文均不泄漏正文", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerPassword({ email: "staging@example.com", password: PASSWORD });
  const marker = "THIS-MUST-NEVER-APPEAR-IN-SQLITE-PLAINTEXT";
  const job = platform.service.createImportJob(user.account.id, "obsidian", {
    sourceLabel: "本地 Vault",
    items: [{ name: "secret.md", path: "private/secret.md", content: marker }],
  }, "encrypted-stage-1");
  assert.equal(job.state, "PENDING");
  assert.equal(Object.hasOwn(job, "selectionEncrypted"), false);
  const raw = platform.store.db.prepare("SELECT selection_json AS selectionJson,selection_encrypted AS selectionEncrypted FROM import_jobs WHERE id=?").get(job.id);
  assert.equal(raw.selectionJson, "{}");
  assert.ok(raw.selectionEncrypted.startsWith("v1."));
  assert.equal(JSON.stringify(raw).includes(marker), false);
  const complete = await platform.service.processNextImportJob("test-worker");
  assert.equal(complete.state, "COMPLETE");
  const stored = platform.store.db.prepare("SELECT selection_encrypted AS selectionEncrypted FROM import_jobs WHERE id=?").get(job.id);
  assert.equal(stored.selectionEncrypted, null);
  const note = await platform.service.readNote(user.account.id, platform.service.listNotes(user.account.id)[0].id);
  assert.equal(note.content, marker);
});
