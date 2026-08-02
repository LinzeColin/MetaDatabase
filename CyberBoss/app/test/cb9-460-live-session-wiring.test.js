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
