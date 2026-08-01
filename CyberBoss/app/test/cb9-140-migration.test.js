"use strict";

// CB9-140 兼容迁移 016（AC-010 / AC-013 / AC-041 的 schema 面，AC-004 / AC-044 的落库面）
//
//   AC-010 北京时间权威字段：同一事件同时含 UTC 与 canonical_beijing。
//   AC-013 位置隐私硬门：raw_ip、latitude、longitude、精确地址命中数 = 0。
//   AC-004/044：Companion 会话在库里有稳定归属，重启后取得回来。
//
// AC-013 用的是**结构性**保证，不是运行时过滤：这几列压根不存在。
// 不存在的列不会因为哪天有人忘了脱敏而泄漏；要更精确的定位就得先改表，
// 而改表会被评审看见。运行时过滤挡不住「有人加了一行 INSERT」。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DatabaseSync } = require("node:sqlite");

const MIGRATION = path.join(__dirname, "..", "migrations", "016_original_parity_sessions_time_location.sql");
const SQL = fs.readFileSync(MIGRATION, "utf8");
const ADAPTER = fs.readFileSync(
  path.join(__dirname, "..", "src", "services", "db", "database-adapter.js"), "utf8",
);

// 在一个只有 schema_migrations 的空库上跑迁移，验证它自洽、可重入。
function applied(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-140-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const db = new DatabaseSync(path.join(dir, "t.db"));
  // 夹具用**仓库真实的**前置状态，不自己编。
  //
  // 踩了两次才对：第一版我凭印象写了个 checksum 列（真实列名是
  // checksum_sha256）；第二版只抓 001 的 CREATE TABLE，可那时候还没有
  // checksum_sha256 —— 它是 002 用 ALTER TABLE 加上去的。
  // 编出来的夹具会让测试证明一件没发生的事：孤立测试全绿，真实适配器直接报
  // 「no column named ...」。所以这里按真实顺序跑 001 + 002。
  const sql = (n) => fs.readFileSync(path.join(__dirname, "..", "migrations", n), "utf8")
    .replaceAll(/__MIGRATION_\d+_CHECKSUM__/g, "fixture");
  db.exec(sql("001_runtime_spool.sql"));
  db.exec(sql("002_cb200_retention_and_transitions.sql"));
  db.exec(SQL);
  return db;
}

test("CB9-140 迁移能在空库上跑通，且 integrity_check 干净", (t) => {
  const db = applied(t);
  const rows = db.prepare("PRAGMA integrity_check").all();
  assert.equal(rows[0].integrity_check, "ok");
});

test("CB9-140 只会被执行一次——由 runner 按 version 保证，不是靠 SQL 幂等", () => {
  // 我一开始写的是「跑两次不炸」，那是我发明的性质：015 用的也是裸 INSERT，
  // 重复执行必然撞 UNIQUE。仓库的真实保证在 runner 里——它从
  // versions.length+1 开始只跑没跑过的那些。照着真实约定断言，不要求 SQL 自己幂等。
  assert.match(ADAPTER, /for\s*\(\s*let nextVersion = versions\.length \+ 1;/);
  assert.match(ADAPTER, /nextVersion <= MIGRATIONS\.length/);
  // 建表语句仍用 IF NOT EXISTS：万一某次执行在中途断了，重来一次不会卡在建表上。
  const creates = SQL.match(/CREATE TABLE[^(]*/g) || [];
  assert.ok(creates.length >= 3, "建表语句少于 3 条");
  for (const c of creates) {
    assert.match(c, /IF NOT EXISTS/, `建表没加 IF NOT EXISTS：${c.trim()}`);
  }
});

test("CB9-140 三张表都建出来了", (t) => {
  const db = applied(t);
  const names = db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((r) => r.name);
  for (const t2 of ["agent_sessions_v009", "user_location_profiles_v009", "parity_receipts_v009"]) {
    assert.ok(names.includes(t2), `缺表 ${t2}`);
  }
});

// ── AC-013 位置隐私硬门 ─────────────────────────────────────

test("AC-013 位置表里不存在 raw_ip / latitude / longitude / 精确地址列", (t) => {
  const db = applied(t);
  const cols = db.prepare("PRAGMA table_info(user_location_profiles_v009)").all().map((c) => c.name);
  const FORBIDDEN = /^(raw_ip|ip|ip_address|latitude|lat|longitude|lng|lon|precise_address|street|postal_code|geohash)$/i;
  const bad = cols.filter((c) => FORBIDDEN.test(c));
  assert.deepEqual(bad, [], `位置表出现了精确定位列：${bad.join(", ")}`);
  // 反面：粗粒度的那几列必须在，否则「只到时区/城市」无从谈起
  for (const need of ["timezone", "coarse_city", "coarse_country", "confidence", "confirmed"]) {
    assert.ok(cols.includes(need), `缺少粗粒度位置列 ${need}`);
  }
});

test("AC-013 整份迁移 SQL 里搜不到精确定位字样", () => {
  const FORBIDDEN = ["raw_ip", "latitude", "longitude", "geohash", "precise_address"];
  for (const word of FORBIDDEN) {
    // 注释里提到「没有 latitude」是允许的，所以只查**列定义**位置：
    // 行首缩进 + 词 + 空格 + 类型。
    const asColumn = new RegExp(`^\\s+${word}\\s+(TEXT|REAL|INTEGER|BLOB|NUMERIC)`, "im");
    assert.ok(!asColumn.test(SQL), `迁移里定义了 ${word} 列`);
  }
});

test("AC-013 confidence 有取值域约束，confirmed 只能是 0/1", (t) => {
  const db = applied(t);
  const ins = (conf, confirmed) => db.prepare(
    `INSERT INTO user_location_profiles_v009
     (user_id,timezone,source,confidence,confirmed,consent_scope,observed_at_utc,updated_at_utc)
     VALUES (?,?,?,?,?,?,?,?)`,
  ).run(`u${conf}${confirmed}`, "Asia/Shanghai", "browser", conf, confirmed, "tz_only", "t", "t");
  ins(0.5, 1);
  assert.throws(() => ins(1.5, 0), /CHECK|constraint/i, "confidence 超出 [0,1] 没被拒绝");
  assert.throws(() => ins(0.5, 2), /CHECK|constraint/i, "confirmed 收下了 0/1 之外的值");
});

// ── AC-010 时间列成对 ───────────────────────────────────────

test("AC-010 带时间的表必须 UTC 与北京时间成对", (t) => {
  const db = applied(t);
  const pairs = {
    agent_sessions_v009: ["last_event_at_utc", "last_event_at_beijing"],
    parity_receipts_v009: ["occurred_at_utc", "occurred_at_beijing"],
  };
  for (const [table, cols] of Object.entries(pairs)) {
    const have = db.prepare(`PRAGMA table_info(${table})`).all().map((c) => c.name);
    for (const c of cols) {
      assert.ok(have.includes(c), `${table} 缺 ${c}——只存一个的话，排序和给用户看的时间必有一个是错的`);
    }
  }
});

// ── AC-004 / AC-044 会话归属 ────────────────────────────────

test("AC-004 一个人一个模式只能有一条会话", (t) => {
  const db = applied(t);
  const ins = (uid, mode, key) => db.prepare(
    `INSERT INTO agent_sessions_v009
     (user_id,mode,session_key,runtime_kind,created_at_utc,updated_at_utc)
     VALUES (?,?,?,?,?,?)`,
  ).run(uid, mode, key, "codex", "t", "t");
  ins("u1", "COMPANION", "comp_a");
  ins("u1", "OWNER", "own_a");        // 同人不同模式，允许
  assert.throws(() => ins("u1", "COMPANION", "comp_b"), /UNIQUE|constraint/i,
    "同一个人同一模式建出了第二条会话");
});

test("AC-044 session_key 全局唯一——两个人不能撞进同一条会话", (t) => {
  const db = applied(t);
  const ins = (uid, key) => db.prepare(
    `INSERT INTO agent_sessions_v009
     (user_id,mode,session_key,runtime_kind,created_at_utc,updated_at_utc)
     VALUES (?,'COMPANION',?,?,?,?)`,
  ).run(uid, key, "deepseek", "t", "t");
  ins("u1", "comp_same");
  assert.throws(() => ins("u2", "comp_same"), /UNIQUE|constraint/i, "两个用户共用了一个 session_key");
});

test("AC-044 mode 和 state 只收合法值", (t) => {
  const db = applied(t);
  const ins = (mode, state) => db.prepare(
    `INSERT INTO agent_sessions_v009
     (user_id,mode,session_key,runtime_kind,state,created_at_utc,updated_at_utc)
     VALUES (?,?,?,?,?,?,?)`,
  ).run(`u${mode}${state}`, mode, `k${mode}${state}`, "codex", state, "t", "t");
  ins("OWNER", "active");
  assert.throws(() => ins("ADMIN", "active"), /CHECK|constraint/i, "收下了 OWNER/COMPANION 之外的模式");
  assert.throws(() => ins("OWNER", "zombie"), /CHECK|constraint/i, "收下了非法状态");
});

// ── 回执脱敏（AC-043 的 schema 面）──────────────────────────

test("回执表存的是哈希不是原值——它要进 Status 和公开页", (t) => {
  const db = applied(t);
  const cols = db.prepare("PRAGMA table_info(parity_receipts_v009)").all().map((c) => c.name);
  assert.ok(cols.includes("user_scope_hash"), "缺 user_scope_hash");
  assert.ok(cols.includes("session_key_hash"), "缺 session_key_hash");
  assert.ok(!cols.includes("user_scope"), "回执表直接存了 user_scope 原值");
  assert.ok(!cols.includes("session_key"), "回执表直接存了 session_key 原值");
});

test("real_path_verified 存在——Status 不许配置性伪绿靠它", (t) => {
  const db = applied(t);
  const cols = db.prepare("PRAGMA table_info(parity_receipts_v009)").all().map((c) => c.name);
  assert.ok(cols.includes("real_path_verified"));
  const ins = (v) => db.prepare(
    `INSERT INTO parity_receipts_v009
     (receipt_id,capability_id,mode,real_path_verified,outcome,occurred_at_utc,occurred_at_beijing)
     VALUES (?,?,?,?,?,?,?)`,
  ).run(`r${v}`, "timeline", "SYSTEM", v, "success", "t", "t");
  ins(1);
  assert.throws(() => ins(2), /CHECK|constraint/i, "real_path_verified 收下了 0/1 之外的值");
});

// ── 注册（漏了这一步迁移永远不会被执行）─────────────────────

test("CB9-140 迁移已在 MIGRATIONS 数组里注册", () => {
  // 这个仓最熟悉的坏法：文件写好了、语法也对，但没登记，于是永远不跑，
  // 而所有单测都绿——因为它们直接 exec 了 SQL 文件。
  assert.match(ADAPTER, /name:\s*"016_original_parity_sessions_time_location\.sql"/);
  assert.match(ADAPTER, /version:\s*14/);
});
