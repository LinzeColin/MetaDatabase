"use strict";

// CB9-500 收尾：把回执接到真实链路上（AC-002 / AC-025）
//
// 在此之前 `parity_receipts_v009` 两头都没有人：
//
//   没人写——recordParityReceipt 全仓零调用者。
//   没人读——collectStatusFacts 从来没产出过 ownerLastSuccessAt 那四个 fact，
//           于是 live-status-projector 里的 `facts.ownerLastSuccessAt ?? null`
//           永远拿到 null。
//
// 后果是 AC-025 的四种状态里，生产上**只可能出现 UNKNOWN**：
//
//   配置存在但没有 live receipt → UNKNOWN   ← 永远停在这一格
//   新鲜的成功                  → HEALTHY
//   过期                        → DEGRADED
//   最近一次失败                → UNAVAILABLE
//
// 而 UNKNOWN 看起来和「刚部署完还没人用」一模一样，所以这个洞不会有任何症状。
// 任务包的目标原话是「以真实链路回执驱动 …… status」，这一整条就是那句话。
//
// 这个文件里最重要的不是回执算得对不对，是**真实投递确认点上到底有没有人调它**，
// 以及调完之后 Status 那边到底看不看得见。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { UserAdmissionService } = require("../src/core/user-admission");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { freshnessOf } = require("../src/services/status/parity-freshness");
const { touchLiveSession } = require("../src/services/timeline/live-session-store");

const ENCRYPTION_KEY = Buffer.alloc(32, 3);
const IDENTITY_KEY = Buffer.alloc(32, 5);
const BOT = "bot-receipts";
const OWNER_SENDER = "owner-sender-receipts";

// 真实的准入层 + 真实的库。密钥不在这里造——从 admission 身上取，
// 因为「测试自己造输入形状」正是 F9 那个故障能活下来的原因。
function harness(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-receipt-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: [OWNER_SENDER],
    registrationMode: "invite",
  });
  const app = {
    runtimeSpoolDatabase: spool,
    userAdmission: admission,
    recordDeliveryReceipt: CyberbossApp.prototype.recordDeliveryReceipt,
    collectParityFreshness: CyberbossApp.prototype.collectParityFreshness,
    formatOwnerLocalTime: CyberbossApp.prototype.formatOwnerLocalTime,
  };
  return { app, spool, admission, directory };
}

// 让主人这条身份真的存在，并且有一条会话可以挂。
function seedOwnerSession(spool, admission) {
  admission.admit({ botAccountRef: BOT, senderRef: OWNER_SENDER, text: "你好" });
  const row = admission.users.resolveByPrincipal({
    channel: "weixin", botAccountRef: BOT, senderRef: OWNER_SENDER,
  });
  assert.ok(row?.user_id, "主人没有被认出来——后面的回执全都无从谈起");
  touchLiveSession(spool.database, {
    userId: row.user_id, mode: "OWNER", runtimeKind: "codex",
    secret: admission.companionSessionSecret,
  });
  return row.user_id;
}

const receipts = (spool) => spool.database
  .prepare("SELECT * FROM parity_receipts_v009 ORDER BY occurred_at_utc")
  .all();

// ── 回执真的落库 ─────────────────────────────────────────

test("AC-025 一次成功投递换一条回执，而且带得上会话钥匙", (t) => {
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);

  const mode = CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
    userId, capabilityId: "wechat_channel", outcome: "success",
  });
  assert.equal(mode, "OWNER", "主人被判成了 COMPANION");

  const rows = receipts(spool);
  assert.equal(rows.length, 1, "投递确认之后表里没有回执");
  assert.equal(rows[0].mode, "OWNER");
  assert.equal(rows[0].outcome, "success");
  assert.equal(rows[0].real_path_verified, 1);
  // AC-002 判的就是「所有回执的 session_key 逻辑身份相同」——没有钥匙就没法判。
  assert.ok(rows[0].session_key_hash, "回执没带上会话钥匙——AC-002 无从判定");
  assert.ok(rows[0].user_scope_hash, "回执没带上用户范围");
});

test("AC-043 回执里存的是哈希，原值一个都不许进去", (t) => {
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);
  CyberbossApp.prototype.recordDeliveryReceipt.call(app, { userId, outcome: "success" });
  const row = receipts(spool)[0];
  const blob = JSON.stringify(row);
  assert.ok(!blob.includes(userId), "user_id 原值进了回执");
  assert.ok(!blob.includes(OWNER_SENDER), "微信发信人原值进了回执");
});

test("AC-002 同一个人连着五种事件，回执上的会话钥匙必须是同一个", (t) => {
  // AC-002 的原话：同一 Owner 依次发普通消息、建提醒、触发提醒、脉冲、审批，
  // 所有回执的 session_key 逻辑身份相同。
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);
  for (const capability of [
    "wechat_channel", "system.reminder", "system.reminder", "system.checkin", "system.system",
  ]) {
    CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
      userId, capabilityId: capability, outcome: "success",
    });
  }
  const keys = new Set(receipts(spool).map((row) => row.session_key_hash));
  assert.equal(keys.size, 1, `五种事件落在了 ${keys.size} 条会话上`);
  assert.equal(receipts(spool).length, 5);
});

test("AC-025 投递失败记成 failure，不是干脆不记", (t) => {
  // 只记成功的话，一条能力会从「新鲜的成功」直接掉进「过期」，面板显示
  // DEGRADED，而它其实在**明确地坏着**（UNAVAILABLE）。这两态要的处置不一样。
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);
  CyberbossApp.prototype.recordDeliveryReceipt.call(app, { userId, outcome: "failure" });
  assert.equal(receipts(spool)[0].outcome, "failure");
});

// ── Status 那边看不看得见 ────────────────────────────────

test("AC-025 写进去的回执，collectStatusFacts 必须读得回来", (t) => {
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);

  // 一条回执都没有的时候：四个 fact 全是 null，也就是「不知道」。
  const before = CyberbossApp.prototype.collectParityFreshness.call(app);
  assert.deepEqual(before, {
    ownerLastSuccessAt: null, ownerLastFailureAt: null,
    companionLastSuccessAt: null, companionLastFailureAt: null,
  }, "没有回执时不该凭空产出时间戳");

  CyberbossApp.prototype.recordDeliveryReceipt.call(app, { userId, outcome: "success" });
  const after = CyberbossApp.prototype.collectParityFreshness.call(app);
  assert.ok(after.ownerLastSuccessAt, "写进去的回执 Status 读不回来——写了等于没写");
  assert.equal(after.ownerLastFailureAt, null);
  // 主人那条路在用，不该把 Companion 也染绿。
  assert.equal(after.companionLastSuccessAt, null, "两个模式的健康度混在一起了");
});

test("AC-025 四种状态在真实数据下都到得了，不是只有 UNKNOWN", (t) => {
  // 这一条是这个文件的理由。修好之前，生产上这四格里**只可能出现 UNKNOWN**。
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);
  const now = Date.parse("2026-08-02T02:00:00.000Z");

  const stateOf = () => {
    const facts = CyberbossApp.prototype.collectParityFreshness.call(app);
    return freshnessOf({
      configured: true,
      lastSuccessAt: facts.ownerLastSuccessAt,
      lastFailureAt: facts.ownerLastFailureAt,
      now,
    }).state;
  };

  assert.equal(stateOf(), "UNKNOWN", "没有回执时不是 UNKNOWN");

  CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
    userId, outcome: "success", now: new Date(now - 60_000),
  });
  assert.equal(stateOf(), "HEALTHY", "新鲜的成功没变成 HEALTHY");

  CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
    userId, outcome: "failure", now: new Date(now - 30_000),
  });
  assert.equal(stateOf(), "UNAVAILABLE", "最近一次失败没变成 UNAVAILABLE");

  // 把那条失败推远，只留一次很旧的成功 → 过期。
  spool.database.exec("DELETE FROM parity_receipts_v009 WHERE outcome='failure'");
  spool.database.prepare("UPDATE parity_receipts_v009 SET occurred_at_utc=?")
    .run(new Date(now - 3 * 60 * 60 * 1000).toISOString());
  assert.equal(stateOf(), "DEGRADED", "旧的成功没变成 DEGRADED");
});

// ── 真实链路上到底有没有人调它 ───────────────────────────

test("AC-025 投递确认点上真的接了回执，不是留了个参数没人传", () => {
  // 这个仓刚在会话表上栽过一次：模块写好了、参数留好了、测试全绿，
  // 而**构造的时候没传**，于是真实链路上一条都不产生（F9）。
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = source.indexOf("new DurableOutboxWorker({");
  assert.ok(start > 0, "找不到 outbox worker 的构造点");
  const body = source.slice(start, source.indexOf("});", start));
  assert.ok(body.includes("onDelivery:"),
    "构造 outbox worker 时没传 onDelivery——普通消息那条路一条回执都不会产生");
  assert.ok(body.includes("this.recordDeliveryReceipt("),
    "onDelivery 没接到回执层");

  // 系统直回那条路（提醒到点、脉冲、checkin、入门引导）的共同落点。
  const noteStart = source.indexOf("  noteBotInitiated({");
  const noteBody = source.slice(noteStart, source.indexOf("  noteDirectReply(", noteStart));
  assert.ok(noteBody.includes("this.recordDeliveryReceipt("),
    "系统直回没接回执——提醒和脉冲永远换不来绿色");
  assert.ok(noteBody.includes("delivered ?"),
    "回执没照实记投递结果——发失败的也会被记成成功");

  // 而 Status 那边要真的去读。
  // 按方法边界取，不按字符数——那句在 return 块里，离方法头挺远，
  // 拿固定长度的窗口去截会漏掉它，而漏掉的表现是这条守卫悄悄失效。
  const factsStart = source.indexOf("  collectStatusFacts() {");
  assert.ok(factsStart > 0, "找不到 collectStatusFacts");
  const factsBody = source.slice(factsStart, source.indexOf("\n  }\n", factsStart));
  assert.ok(factsBody.includes("this.collectParityFreshness()"),
    "collectStatusFacts 没读回执——写进去的东西 Status 看不见");
});

test("AC-025 outbox 在确认和终态失败两处都会回调，ambiguous 不回调", () => {
  // ambiguous 是「不知道送没送到」。记成失败会把一次可能成功的投递说成故障，
  // 而这套面板最不该做的就是指着一个不存在的故障。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "outbox", "durable-outbox.js"), "utf8");
  const confirmAt = source.indexOf('return "confirmed";');
  assert.ok(source.slice(confirmAt - 400, confirmAt).includes("#notifyDelivery"),
    "投递确认之后没有回调——成功换不来绿色");
  const terminalAt = source.indexOf('return ambiguous ? "ambiguous" : "terminal";');
  const terminalBody = source.slice(terminalAt - 700, terminalAt);
  assert.ok(terminalBody.includes("#notifyDelivery"), "终态失败没有回调");
  assert.ok(/if \(!ambiguous\)/.test(terminalBody),
    "ambiguous 也被记成失败了——一次可能成功的投递会被说成故障");
});

test("AC-025 回执记账挂掉不能把已经送到的消息带走", () => {
  // 回执是旁路。它抛异常时如果没人兜，durable-outbox 的 catch 会把一条**已经
  // 送到用户手机上**的消息当成投递失败，然后重发——用户收到两条一样的话。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "outbox", "durable-outbox.js"), "utf8");
  const start = source.indexOf("  #notifyDelivery(userId, outcome) {");
  assert.ok(start > 0, "找不到回调的落点");
  const body = source.slice(start, source.indexOf("\n  }", start));
  assert.ok(/try \{/.test(body) && /catch/.test(body),
    "回执回调没有兜住异常——它一抛，已经送到的消息会被当成失败重发");
});

test("AC-025 同一毫秒里的两条同类回执不许合并成一条", (t) => {
  // 回执 id 原来是从 capability + mode + 时间 + userScope 推出来的。会话钥匙
  // 必须那样推（它是稳定身份），但回执是**事件**——同一个人同一项能力在同一
  // 毫秒里发生两次完全正常（两条提醒同时到点），而推出来的 id 一模一样，
  // 第二条撞主键、被 catch 吞掉，一条真实发生过的投递从账上消失。
  const { app, spool, admission } = harness(t);
  const userId = seedOwnerSession(spool, admission);
  const sameInstant = new Date("2026-08-02T02:00:00.000Z");
  for (let i = 0; i < 3; i += 1) {
    CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
      userId, capabilityId: "system.reminder", outcome: "success", now: sameInstant,
    });
  }
  assert.equal(receipts(spool).length, 3, "同一毫秒的三条回执合并了——真实投递从账上消失");
});

test("AC-025 回执 id 不许再从内容推出来", () => {
  // 结构性的：上面那条靠「同一毫秒」触发，而 Date 精度一变它就可能自己变绿。
  // 直接查算料——够不着比「我们没用」强。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "timeline", "live-session-store.js"), "utf8");
  // 直接找那一行，不切函数体：函数体里有多行模板字符串，按 "\n}" 找结尾会
  // 提前截断，而截断的表现是这条守卫悄悄失效（切出来是空串，两条断言都过）。
  const at = source.indexOf("`rcpt_");
  assert.ok(at > 0, "找不到回执 id 的生成处");
  // 切到行尾为止。取固定长度会越进下一行——那一行上正好有 String(capabilityId)，
  // 于是这条守卫会因为看见下一行的东西而误报。
  const idLine = source.slice(at, source.indexOf("\n", at));
  assert.ok(idLine.includes("randomBytes"), "回执 id 又变回从内容推了");
  assert.ok(!idLine.includes("capabilityId") && !idLine.includes("utc"),
    "回执 id 的算料里还有内容——同一毫秒的两条会撞主键");
});

test("AC-025 两个模式各算各的，一条路在用不能把另一条染绿", (t) => {
  // 上一条「两个模式的健康度混在一起了」是**松的**：它只写了主人一个模式的
  // 回执，于是 GROUP BY mode 去掉之后照样绿（只有一个模式，聚合结果一样）。
  // 变异测试抓到了这一刀。
  //
  // 真正承重的是两个模式**同时有数据**的时候：不分组的话 SQLite 会把两边
  // 聚成一行，其中一个模式拿到另一个模式的时间戳——主人那条路一直在用，
  // 就能把 Companion 的故障盖成绿色，而那正是伪绿。
  const { app, spool, admission } = harness(t);
  const ownerId = seedOwnerSession(spool, admission);

  const invite = admission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
  admission.admit({ botAccountRef: BOT, senderRef: "guest-1", text: invite.code });
  const guest = admission.admit({ botAccountRef: BOT, senderRef: "guest-1", text: "你好" });
  assert.equal(guest.route, "user", "访客没开通成功");
  const guestId = guest.userContext.userId;
  touchLiveSession(spool.database, {
    userId: guestId, mode: "COMPANION", runtimeKind: "provider",
    secret: admission.companionSessionSecret,
  });

  const ownerAt = new Date("2026-08-02T02:00:00.000Z");
  const guestAt = new Date("2026-08-02T01:00:00.000Z");
  CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
    userId: ownerId, outcome: "success", now: ownerAt,
  });
  CyberbossApp.prototype.recordDeliveryReceipt.call(app, {
    userId: guestId, outcome: "failure", now: guestAt,
  });

  const facts = CyberbossApp.prototype.collectParityFreshness.call(app);
  assert.equal(facts.ownerLastSuccessAt, ownerAt.toISOString(), "主人的成功时间不对");
  assert.equal(facts.ownerLastFailureAt, null, "访客的失败算到了主人头上");
  assert.equal(facts.companionLastFailureAt, guestAt.toISOString(), "访客的失败丢了");
  assert.equal(facts.companionLastSuccessAt, null,
    "主人的成功把访客那条路染绿了——那是伪绿");
});
