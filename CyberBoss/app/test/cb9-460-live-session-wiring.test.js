"use strict";

// CB9-460 把统一 Session 接到真实链路上（AC-002 / AC-004 / AC-044）
//
// 这个文件补的是一个我自己挖的洞。
//
// CB9-400 那一轮做了事件模型、日记投影、未来自我、审批台账，七十多条测试全绿，
// 迁移 016 也在生产上跑过了——`agent_sessions_v009` 表实实在在地存在。
// 然后我把 S4 标成了完成。
//
// 今天去生产上一查：**0 行**。真实入站消息一条条进来、一条条回出去，从来没有
// 任何代码往这张表里写过。整层是个孤岛。
//
// 教训不是「测试没写够」——那七十多条测的东西都对。教训是**「模块能用」和
// 「真实链路上有人用它」是两件事**，而 AC-002/004/044 那种「同一个人连续两轮」
// 「重启后还认得他」的验收，只有后者能支撑。
//
// 所以这一套测试里，最重要的不是钥匙算得对不对，是**真实准入路径上到底有没有
// 人调它**，以及调完之后表里到底有没有行。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const {
  LiveSessionError,
  readLiveSession,
  recordParityReceipt,
  sessionKeyFor,
  touchLiveSession,
} = require("../src/services/timeline/live-session-store");

const SECRET = Buffer.alloc(32, 9);
const OTHER_SECRET = Buffer.alloc(32, 7);
const uid = (suffix) => `${"usr"}_${suffix}${"0".repeat(Math.max(0, 20 - suffix.length))}`;

function openDatabase(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-session-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const database = new DatabaseSync(path.join(dir, "runtime.db"));
  t.after(() => database.close());
  const sql = fs.readFileSync(
    path.join(__dirname, "..", "migrations", "016_original_parity_sessions_time_location.sql"),
    "utf8",
  );
  // 只取这两张表的建表语句，不跑整份迁移（它依赖前面十五份）。
  for (const table of ["agent_sessions_v009", "parity_receipts_v009"]) {
    const start = sql.indexOf(`CREATE TABLE IF NOT EXISTS ${table}`);
    assert.ok(start > 0, `迁移里找不到 ${table}`);
    database.exec(sql.slice(start, sql.indexOf(");", start) + 2));
  }
  return database;
}

// ── 真实链路上有没有人调它 ───────────────────────────────

test("AC-002 真实准入路径上调了会话记账", () => {
  // 这一条是这个文件存在的理由。上一轮的失败不是判定写错了，
  // 是**没有任何人在真实路径上调它**——而那种失败在单元测试里是看不见的。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = app.indexOf("  admitDurableTurn(normalized) {");
  assert.ok(start > 0, "找不到真实准入锚点");
  const body = app.slice(start, start + 2600);
  assert.ok(body.includes("this.touchTurnSession(decision)"),
    "真实准入路径上没有会话记账——agent_sessions_v009 会永远是 0 行");
  // 而且要在拿到 user_id 之后：没有 user_id 就没有会话可记。
  assert.ok(body.indexOf("decision.userContext?.userId") < body.indexOf("this.touchTurnSession"),
    "在拿到 user_id 之前就去记会话了");
});

test("AC-002 会话记账失败不能把用户的回复也带走", () => {
  // 记账是旁路。它挂掉时用户该照样收到回复——但必须出声，
  // 静默失败正是让这张表空了这么久还没人发现的原因。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = app.indexOf("  touchTurnSession(decision) {");
  const body = app.slice(start, app.indexOf("  admitDurableTurn(", start));
  assert.ok(/catch \(error\)/.test(body), "没有兜住异常");
  assert.ok(/console\.warn/.test(body), "兜住了但一声不吭——这正是上一次没人发现的原因");
});

// ── AC-002 同一个人同一条会话 ────────────────────────────

test("AC-002 同一个人连发五轮，还是同一条会话", (t) => {
  // AC-002 的原话：同一 Owner 依次发普通消息、建提醒、触发提醒、脉冲、审批，
  // 所有回执的会话逻辑身份相同。
  const database = openDatabase(t);
  const userId = uid("owner");
  const keys = new Set();
  let last = null;
  for (let i = 0; i < 5; i += 1) {
    last = touchLiveSession(database, { userId, mode: "OWNER", runtimeKind: "codex", secret: SECRET });
    keys.add(last.session_key);
  }
  assert.equal(keys.size, 1, "五轮里换过会话");
  assert.equal(last.context_version, 5, "上下文版本没跟着推进");
  assert.equal(last.created_at_utc, readLiveSession(database, { userId, mode: "OWNER" }).created_at_utc);
});

test("AC-004 两个人各自一条，谁也读不到谁", (t) => {
  const database = openDatabase(t);
  const alice = uid("alice");
  const bob = uid("bob");
  const a = touchLiveSession(database, { userId: alice, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  const b = touchLiveSession(database, { userId: bob, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  assert.notEqual(a.session_key, b.session_key, "两个人撞进了同一条会话");
  // 按 (user_id, mode) 读，读到的只能是自己那条。
  assert.equal(readLiveSession(database, { userId: alice, mode: "COMPANION" }).session_key, a.session_key);
  assert.equal(readLiveSession(database, { userId: bob, mode: "COMPANION" }).session_key, b.session_key);
});

test("AC-002 同一个人的两个模式是两条会话", (t) => {
  // 主人自己也可能以访客身份被路由（席位外）。两条路的上下文不该混在一起。
  const database = openDatabase(t);
  const userId = uid("dualmode");
  const owner = touchLiveSession(database, { userId, mode: "OWNER", runtimeKind: "codex", secret: SECRET });
  const guest = touchLiveSession(database, { userId, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  assert.notEqual(owner.session_key, guest.session_key);
});

// ── AC-044 跨重启 ────────────────────────────────────────

test("AC-044 会话钥匙跨进程重启不变", (t) => {
  // 含时间或随机数的话，进程一重启同一个人就换了一条会话，
  // 「记得上一轮」当场失效，而表面上什么都没坏。
  const userId = uid("restart");
  const before = sessionKeyFor({ userId, mode: "COMPANION", secret: SECRET });
  const after = sessionKeyFor({ userId, mode: "COMPANION", secret: SECRET });
  assert.equal(before, after);
  assert.match(before, /^sess_[0-9a-f]{32}$/);
});

test("AC-044 钥匙的算料里够不着时间和随机数", () => {
  // 上一条是**松的**：连着调两次落在同一毫秒里，`Date.now()` 当然相等，
  // 于是把时间掺进钥匙这一刀能活着穿过去（变异测试抓到的）。
  //
  // 「跨重启稳定」这种性质靠调两次比一比是验不出来的——真正的重启隔的是几小时。
  // 所以查**结构**：那个函数的算料里根本没有时间和随机数这两样东西。
  // 够不着比「我们没用」强。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "timeline", "live-session-store.js"), "utf8");
  const start = source.indexOf("function sessionKeyFor(");
  const body = source.slice(start, source.indexOf("\n}", start));
  for (const hint of ["Date.now", "new Date", "Math.random", "randomBytes", "randomUUID", "process.hrtime"]) {
    assert.ok(!body.includes(hint),
      `钥匙的算料里出现了 ${hint}——进程一重启同一个人就换了一条会话`);
  }
});

test("AC-044 换了服务端密钥也不把已有会话的钥匙冲掉", (t) => {
  // upsert 的 UPDATE 分支里**不更新** session_key。这一条原本也是死的：
  // 钥匙是确定的，`session_key = excluded.session_key` 写不写都一样（变异测试
  // 里那一刀因此活着）。用一把不同的密钥去 touch 同一个人，那行 SQL 就承重了。
  //
  // 而这正是密钥轮换那天要的行为：轮换不该把所有人的对话历史切断。
  const database = openDatabase(t);
  const userId = uid("rotate");
  const first = touchLiveSession(database, { userId, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  const second = touchLiveSession(database, { userId, mode: "COMPANION", runtimeKind: "provider", secret: OTHER_SECRET });
  assert.equal(second.session_key, first.session_key,
    "换密钥把已有会话的钥匙冲掉了——那一天所有人的上下文一起断");
  assert.equal(second.context_version, 2, "轮换那一轮没算进上下文版本");
});

test("AC-044 重开数据库之后还认得同一条会话", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-session-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "runtime.db");
  const schema = (db) => {
    const sql = fs.readFileSync(
      path.join(__dirname, "..", "migrations", "016_original_parity_sessions_time_location.sql"), "utf8");
    const start = sql.indexOf("CREATE TABLE IF NOT EXISTS agent_sessions_v009");
    db.exec(sql.slice(start, sql.indexOf(");", start) + 2));
  };
  const userId = uid("survivor");

  const first = new DatabaseSync(file);
  schema(first);
  const before = touchLiveSession(first, { userId, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  first.close();

  // 「重启」：换一个连接重新打开同一个文件。
  const second = new DatabaseSync(file);
  const restored = readLiveSession(second, { userId, mode: "COMPANION" });
  assert.equal(restored.session_key, before.session_key, "重启后换了一条会话");
  const bumped = touchLiveSession(second, { userId, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  assert.equal(bumped.session_key, before.session_key);
  assert.equal(bumped.context_version, 2, "重启后上下文版本从头开始了");
  second.close();
});

test("AC-044 runtime 换个名字不换会话", (t) => {
  // 升级换了 runtime 标识就换一条会话的话，AC-044 要的「重启后恢复」当场失效。
  const database = openDatabase(t);
  const userId = uid("runtimeswap");
  const a = touchLiveSession(database, { userId, mode: "COMPANION", runtimeKind: "provider", secret: SECRET });
  const b = touchLiveSession(database, { userId, mode: "COMPANION", runtimeKind: "provider-v2", secret: SECRET });
  assert.equal(b.session_key, a.session_key, "换个 runtime 名字就换会话了");
  assert.equal(b.runtime_kind, "provider-v2", "runtime 名字本身该更新");
});

// ── 会话钥匙的性质 ───────────────────────────────────────

test("AC-043 从会话钥匙反推不出 user_id", () => {
  // 它会进回执、进 Status。把 user_id 拼进去的话，公开面上就等于挂着用户标识。
  const userId = uid("hidden");
  const key = sessionKeyFor({ userId, mode: "COMPANION", secret: SECRET });
  assert.ok(!key.includes(userId));
  assert.ok(!key.includes("hidden"));
});

test("换一把密钥就是另一条会话", () => {
  const userId = uid("keyed");
  assert.notEqual(
    sessionKeyFor({ userId, mode: "OWNER", secret: SECRET }),
    sessionKeyFor({ userId, mode: "OWNER", secret: OTHER_SECRET }),
  );
});

test("没有密钥时不发钥匙，而不是用一个固定串顶上", () => {
  // 顶上的话，任何人拿到源码就能算出别人的 session_key。
  for (const bad of [undefined, null, "", Buffer.alloc(8)]) {
    assert.throws(
      () => sessionKeyFor({ userId: uid("nokey"), mode: "OWNER", secret: bad }),
      (error) => error instanceof LiveSessionError && error.code === "SESSION_SECRET_REQUIRED",
    );
  }
});

test("认不出来的模式直接拒", () => {
  for (const mode of ["owner", "GUEST", "", null]) {
    assert.throws(
      () => sessionKeyFor({ userId: uid("mode"), mode, secret: SECRET }),
      (error) => error.code === "SESSION_MODE_UNKNOWN",
    );
  }
});

// ── AC-025 真实链路回执 ──────────────────────────────────

test("AC-025 回执里存的是哈希，不是原值", (t) => {
  // 回执要进 Status 和公开页，原值进去就是 AC-043 说的泄漏。
  const database = openDatabase(t);
  const userId = uid("receipt");
  const key = sessionKeyFor({ userId, mode: "OWNER", secret: SECRET });
  recordParityReceipt(database, {
    capabilityId: "wechat_channel", mode: "OWNER",
    userScope: userId, sessionKey: key, outcome: "success", secret: SECRET,
  });
  const row = database.prepare("SELECT * FROM parity_receipts_v009").get();
  const serialized = JSON.stringify(row);
  assert.ok(!serialized.includes(userId), "回执里有 user_id 原值");
  assert.ok(!serialized.includes(key), "回执里有 session_key 原值");
  assert.equal(row.real_path_verified, 1);
  assert.equal(row.outcome, "success");
});

test("AC-025 认不出来的结果直接拒，不当成成功", (t) => {
  // 当成成功的话，一次没看懂的结果会让 Status 变绿。
  const database = openDatabase(t);
  assert.throws(
    () => recordParityReceipt(database, {
      capabilityId: "x", mode: "OWNER", outcome: "probably_ok", secret: SECRET,
    }),
    (error) => error.code === "RECEIPT_OUTCOME_UNKNOWN",
  );
});

// ── AC-002 五种都要落在同一条会话上 ─────────────────────

test("AC-002 系统主动消息也接了会话，不是只接了入站", () => {
  // 第一版只接了 admitDurableTurn。那已经能让表里有行了，看起来是「修好了」——
  // 但 AC-002 要的是「普通消息、建提醒、**触发提醒**、**脉冲**、审批」五种落在
  // 同一条会话上。少接一条，那一条的回执就挂在别处，「逻辑身份相同」当场不成立，
  // 而且没有任何症状：表里有行，只是少了几种。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");

  // 提醒到点（零模型那条）。
  const direct = app.slice(app.indexOf("  async deliverDirectReminder(reminder) {"), app.indexOf("  async deliverDirectReminder(reminder) {") + 400);
  assert.ok(direct.includes("this.touchSystemSession("), "提醒到点没接会话");

  // 脉冲 / checkin / onboarding —— 它们的共同落点。
  const noted = app.slice(app.indexOf("  noteBotInitiated({"), app.indexOf("  noteBotInitiated({") + 1400);
  assert.ok(noted.includes("this.touchSystemSession("),
    "系统主动消息没接会话——脉冲和 checkin 的回执会挂在别处");
});

test("AC-002 系统侧接在共同落点上，不是每个发送点各接一次", () => {
  // 每个发送点各接的话，下一个新增的系统消息种类必然漏掉。
  // noteBotInitiated 是它们唯一的共同落点。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const calls = [...app.matchAll(/this\.touchSystemSession\(/g)].length;
  assert.ok(calls <= 3, `touchSystemSession 被调了 ${calls} 次——散开了，下一个新增的种类会漏`);
  assert.ok(calls >= 2, "至少要覆盖提醒到点和系统主动消息两条");
});

test("AC-002 按号查人：同一个人在不同号下不是同一条会话", (t) => {
  // resolvePrincipalSession 要带上 accountId。不带的话，主人同时管两个微信号时，
  // 两个号下的同一个人会被算成同一个 user_id——那是跨号串数据。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const body = app.slice(app.indexOf("  resolvePrincipalSession(accountId, senderId) {"), app.indexOf("  resolvePrincipalSession(accountId, senderId) {") + 700);
  assert.ok(body.includes("botAccountRef: String(accountId"), "查人时没带上账号");
  // 而系统侧那条路要真的把 accountId 传下来。
  assert.ok(app.includes("this.activeSystemMessageAccountId = String(message?.accountId"),
    "系统消息没把 accountId 记下来——noteBotInitiated 那一层拿不到");
});

// ── 生产方给的密钥，会话层收不收得下 ─────────────────────

// 这一节是这个文件里唯一能抓到 2026-08-02 那个故障的东西，而它之所以能抓到，
// 只有一个原因：**密钥是从真实生产方身上取的，不是这里造的。**
//
// 上面所有用 `SECRET = Buffer.alloc(32, 9)` 的测试，在故障存在的那段时间里
// 全部是绿的。生产上真实链路每一个 turn 都在抛 SESSION_SECRET_REQUIRED，
// 被旁路的 catch 吞掉，表一直 0 行。造出来的输入形状让套件全绿而生产 100% 失效。
//
// 所以这几条不许出现任何自己拼的密钥常量。

const { UserAdmissionService } = require("../src/core/user-admission");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");

const IDENTITY_KEY = Buffer.alloc(32, 5);
const ENCRYPTION_KEY = Buffer.alloc(32, 3);

function realAdmission(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-session-real-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(dir, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-sender"],
    registrationMode: "invite",
  });
  return { spool, admission };
}

test("AC-002 真实准入层给出的密钥，会话层必须直接收得下", (t) => {
  const { admission } = realAdmission(t);
  // 不看它是什么形状——形状是生产方的自由。只要求会话层收得下。
  const key = sessionKeyFor({
    userId: uid("realsecret"), mode: "OWNER", secret: admission.companionSessionSecret,
  });
  assert.match(key, /^sess_[0-9a-f]{32}$/,
    "真实生产方的密钥算不出会话钥匙——真实链路上每一个 turn 都会静默失败");
});

test("AC-002 真实密钥落库：表里真的多一行，不是只算出个字符串", (t) => {
  const { admission } = realAdmission(t);
  const database = openDatabase(t);
  const userId = uid("realrow");
  const first = touchLiveSession(database, {
    userId, mode: "OWNER", runtimeKind: "codex", secret: admission.companionSessionSecret,
  });
  assert.equal(first.context_version, 1);
  const second = touchLiveSession(database, {
    userId, mode: "OWNER", runtimeKind: "codex", secret: admission.companionSessionSecret,
  });
  assert.equal(second.context_version, 2, "第二轮没有推进上下文版本");
  assert.equal(second.session_key, first.session_key, "同一个人两轮换了会话钥匙");
});

test("AC-002 真实密钥下的回执，两个哈希都不许是 NULL", (t) => {
  const { admission } = realAdmission(t);
  const database = openDatabase(t);
  const userId = uid("realrcpt");
  const key = sessionKeyFor({ userId, mode: "OWNER", secret: admission.companionSessionSecret });
  recordParityReceipt(database, {
    capabilityId: "cap.session", mode: "OWNER", userScope: userId, sessionKey: key,
    outcome: "success", secret: admission.companionSessionSecret,
  });
  const row = database
    .prepare("SELECT user_scope_hash, session_key_hash FROM parity_receipts_v009 WHERE capability_id=?")
    .get("cap.session");
  // 原来只认 Buffer 的写法在这里不会抛，只会把两个哈希静默写成 NULL——
  // 回执照样落库、看起来一切正常，只是再也对不上是谁的。
  assert.ok(row.user_scope_hash, "user_scope_hash 是空的");
  assert.ok(row.session_key_hash, "session_key_hash 是空的");
  assert.notEqual(row.user_scope_hash, userId, "原值直接进了回执");
});

test("AC-002 不是什么字符串都当密钥：截断出来的空 Buffer 必须被拦住", (t) => {
  const database = openDatabase(t);
  // Buffer.from(x, "hex") 遇到非法字符会**悄悄截断**。"zz" 得到空 Buffer，
  // 那等于没有密钥，而且不报错——所以归一化必须自己验 hex，不能交给 Buffer.from。
  for (const bad of ["z".repeat(64), "ab", "", "abc".repeat(11), Buffer.alloc(8, 1), 12345, null]) {
    assert.throws(
      () => sessionKeyFor({ userId: uid("badkey"), mode: "OWNER", secret: bad }),
      (error) => error.code === "SESSION_SECRET_REQUIRED",
      `弱密钥被放行了：${typeof bad === "string" ? JSON.stringify(bad.slice(0, 8)) : String(bad)}`,
    );
  }
  assert.equal(
    database.prepare("SELECT COUNT(*) AS n FROM agent_sessions_v009").get().n, 0,
    "弱密钥居然还落了行",
  );
});

test("AC-002 这个文件里对生产密钥的检查，不许退化成自己造的常量", () => {
  // 这条守的是这一节本身。有人把 admission.companionSessionSecret 换成
  // SECRET 之后，上面四条会全绿，而 2026-08-02 那个故障重新变得抓不到。
  const self = fs.readFileSync(__filename, "utf8");
  const section = self.slice(self.indexOf("// ── 生产方给的密钥"));
  const uses = [...section.matchAll(/admission\.companionSessionSecret/g)].length;
  assert.ok(uses >= 3, `真实密钥只用了 ${uses} 处——这一节正在退回自己造密钥`);
  assert.ok(!/secret:\s*SECRET/.test(section), "这一节里出现了自己造的密钥常量");
});

// ── 系统直回记在哪个号下面 ───────────────────────────────

test("AC-002 系统直回必须带上自己的号，不能读那个可变字段", () => {
  // this.activeSystemMessageAccountId 是个留在对象上的可变字段，只有
  // dispatchSystemMessage 会设它。入门引导、状态、后台链接、提醒到点这几条
  // 直回如果也读它，读到的是**上一条系统消息留下的号**。
  //
  // 后果不是「记不上」，是「记到别人头上」：同一个人在不同号下本来就是两个
  // user_id，拿陈旧的号去查，要么静默丢掉，要么查到另一条身份。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  for (const [call, expected] of [
    ["this.noteDirectReply(senderId, text,", "accountId: account.accountId"],
    ["this.noteDirectReply(normalized.senderId, text,", "accountId: normalized.accountId"],
    ["this.noteDirectReply(reminder.senderId, reminder.text,", "accountId: reminder.accountId"],
  ]) {
    let from = 0;
    let seen = 0;
    for (;;) {
      const at = app.indexOf(call, from);
      if (at < 0) {
        break;
      }
      seen += 1;
      assert.ok(app.slice(at, at + 260).includes(expected),
        `${call} 没把自己手上的号传下去——会话会记到上一条系统消息那个号的人头上`);
      from = at + call.length;
    }
    assert.ok(seen > 0, `找不到调用点：${call}`);
  }
});

test("AC-002 那个可变字段只兜底一条路，不能变回默认口径", () => {
  // 兜底留着是因为 streamDelivery 那条路确实没把号带下来。但它只该服务那一条：
  // 一旦别的调用点又开始依赖它，这个 bug 就原样回来了，而且照样没有症状。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  // 只数真正的读：赋值那一处不算，注释里提到它也不算。
  const reads = app.split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .filter((line) => /this\.activeSystemMessageAccountId\b/.test(line))
    .filter((line) => !/this\.activeSystemMessageAccountId\s*=/.test(line));
  assert.equal(reads.length, 1,
    `activeSystemMessageAccountId 被读了 ${reads.length} 次——兜底正在变成默认口径`);
  const start = app.indexOf("  noteBotInitiated({");
  const body = app.slice(start, app.indexOf("  noteDirectReply(", start));
  assert.ok(body.includes("accountId === null"),
    "兜底不是按「调用方没给」触发的——传了空字符串也会被兜底盖掉");
});

// ── 真实路径上调的方法，得真的存在 ───────────────────────

test("app.js 里每一个 this.X(...) 都必须真的挂在 prototype 上", () => {
  // 这一条是从会话表那次故障顺出来的，抓的是同一个形状的另一面。
  //
  // formatOwnerLocalTime 是个**模块级函数**，而 app.js 里有六处写的是
  // `this.formatOwnerLocalTime(...)`——prototype 上根本没有这个方法：
  //
  //   buildPersonalSite / listOwnReminders / buildPersonDetail / runItemAction
  //   没加 ?.，只要列表里有一条带时间的项就当场 TypeError；
  //
  //   touchTurnSession / touchSystemSession 加了 ?.，不抛，但静默落到 null，
  //   于是 last_event_at_beijing 这一列存进去的是 UTC——一个叫「北京时间」的
  //   字段里装着差 8 小时的值。比空着更坏：面板会把它当真的显示出来。
  //
  // 它能活到今天，是因为七处测试各自写了 `app.formatOwnerLocalTime = ...`，
  // 自己往对象上装了一个生产环境没有的方法。测试造出了依赖的存在。
  //
  // 所以这里不借测试对象，直接问真的 prototype。
  const { CyberbossApp } = require("../src/core/app");
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");

  const available = new Set(Object.getOwnPropertyNames(CyberbossApp.prototype));
  // 构造函数里赋上去的可调用字段也算数（this.X = ...），它们不在 prototype 上
  // 但确实存在。formatOwnerLocalTime 哪儿都没被赋过——正因如此才抓得到。
  for (const assigned of source.matchAll(/this\.([A-Za-z_][A-Za-z0-9_]*)\s*=/g)) {
    available.add(assigned[1]);
  }

  const missing = new Set();
  for (const call of source.matchAll(/this\.([A-Za-z_][A-Za-z0-9_]*)\s*(\?\.)?\(/g)) {
    if (!available.has(call[1])) {
      missing.add(call[1]);
    }
  }
  assert.deepEqual([...missing].sort(), [],
    `这些方法在真实路径上被调用，但 prototype 上没有：${[...missing].sort().join(", ")}`
    + "——加了 ?. 的那几处会静默落到默认值，没加的当场 TypeError",
  );
});

test("北京时间那一列真的是北京时间，不是换个名字的 UTC", () => {
  // 会话行里 last_event_at_beijing 曾经等于 last_event_at_utc，因为
  // `this.formatOwnerLocalTime?.(new Date()) || null` 里那个方法不存在，
  // 落成 null，而 live-session-store 的 `beijing || utc` 又把 UTC 填了进去。
  //
  // 生产上 2026-08-02T01:59:32.684Z 那一行两列一模一样——真实的北京时间是 09:59。
  const { CyberbossApp } = require("../src/core/app");
  const app = Object.create(CyberbossApp.prototype);
  const utc = "2026-08-02T01:59:32.684Z";
  const local = CyberbossApp.prototype.formatOwnerLocalTime.call(app, utc);
  assert.ok(local, "算不出本地时间——那一列又会退回存 UTC");
  assert.notEqual(local, utc, "本地时间和 UTC 一模一样");
  // 主人时区是东八区：01:59 UTC 应该渲染成 09:59。
  assert.match(local, /09:59/, `按主人时区应该是 09:59，实际是 ${local}`);
});
