"use strict";

// CB9-220 信号优先级、置信度、确认与隐私最小化（AC-013 / AC-014）
//
//   AC-014 显式陈述优先于浏览器，浏览器优先于 Cloudflare；冲突低置信时只在
//          首条成功回复后提一次中文确认。
//   AC-013 长期事实不含原始 IP 或精确经纬度。
//
// AC-014 拆开是四件独立的事，写错的表现各不相同：
//   优先级错     → 用 VPN 的人被按出口 IP 的时区安排提醒。
//   置信度错     → 该问的不问，不该问的乱问。
//   「首条之后」错 → 人还没见到第一句回复，先被问了个莫名其妙的问题。
//   「只一次」错   → 每句话后面都跟一句「你是不是在悉尼？」，比不问更烦人。
// 所以四件各有自己的测试，不揉成一条。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

const {
  CONFIRM_BELOW_CONFIDENCE,
  PUBLIC_FIELDS,
  buildConfirmationQuestion,
  mergeLocationSignals,
  publicProjection,
  sameWallClock,
  shouldAskConfirmation,
} = require("../src/services/location/location-profile");
const { safeObservation } = require("../src/services/location/timezone-signals");
const { MIGRATIONS } = require("../src/services/db/database-adapter");

const AT = new Date("2026-07-29T14:48:00.000Z");
const sig = (source, timezone, extra = {}) => safeObservation({ source, timezone, ...extra });

// ── AC-014 一：冻结优先级 ──────────────────────────────────

test("AC-014 显式陈述赢浏览器，浏览器赢 Cloudflare", () => {
  // 任务包 fixtures/timezone-signals.json 的 explicit-wins 与 browser-over-cf
  // 两个用例，原样搬过来当 oracle。
  const all = mergeLocationSignals([
    sig("cloudflare_timezone", "Asia/Shanghai"),
    sig("browser_iana", "Australia/Sydney"),
    sig("explicit_user", "Asia/Tokyo"),
  ], { at: AT });
  assert.equal(all.timezone, "Asia/Tokyo");
  assert.equal(all.source, "explicit_user");

  const noExplicit = mergeLocationSignals([
    sig("cloudflare_timezone", "Asia/Singapore"),
    sig("browser_iana", "Australia/Sydney"),
  ], { at: AT });
  assert.equal(noExplicit.timezone, "Australia/Sydney");
  assert.equal(noExplicit.source, "browser_iana");
});

test("AC-014 顺序无关——信号先后到达不改变谁赢", () => {
  // 按到达顺序取最后一个的实现在这里会红。加入页上 CF 头和浏览器上报的先后
  // 是不确定的。
  const forward = mergeLocationSignals([
    sig("browser_iana", "Australia/Sydney"), sig("cloudflare_timezone", "Asia/Singapore"),
  ], { at: AT });
  const backward = mergeLocationSignals([
    sig("cloudflare_timezone", "Asia/Singapore"), sig("browser_iana", "Australia/Sydney"),
  ], { at: AT });
  assert.equal(forward.timezone, backward.timezone);
  assert.equal(forward.timezone, "Australia/Sydney");
});

test("AC-014 一个信号都没有＝按默认口径办，不是「猜北京」", () => {
  const none = mergeLocationSignals([], { at: AT });
  assert.equal(none.timezone, "Asia/Shanghai");
  assert.equal(none.fallback, true, "没信号必须标出来");
  assert.equal(none.confidence, 0);
  // 差别在于要不要问他：没信号不该问——问了他也答不出所以然，而且这是绝大
  // 多数人的默认状态。fallback 分不出来的话，每个新用户都会被问一遍。
  assert.equal(shouldAskConfirmation({ merged: none, firstReplyDelivered: true }), false);
});

// ── AC-014 二：置信度与冲突 ────────────────────────────────

test("AC-014 冲突会压低置信度", () => {
  // fixtures 的 conflict-confirm：浏览器说悉尼，CF 说奥克兰。
  const conflict = mergeLocationSignals([
    sig("browser_iana", "Australia/Sydney"),
    sig("cloudflare_timezone", "Pacific/Auckland"),
  ], { at: AT });
  assert.equal(conflict.conflict, true);
  assert.ok(conflict.confidence < CONFIRM_BELOW_CONFIDENCE,
    `冲突后置信度 ${conflict.confidence} 仍在阈值之上，不会触发确认`);
  assert.equal(shouldAskConfirmation({ merged: conflict, firstReplyDelivered: true }), true);
});

test("AC-014 只有 Cloudflare 说话，也要问", () => {
  // CF 是按出口 IP 猜的。用 VPN 的人这时候被猜错的概率最高，而且没有第二个
  // 信号能纠正它——所以单独一个 CF 必须落在阈值以下。
  const only = mergeLocationSignals([sig("cloudflare_timezone", "Asia/Singapore")], { at: AT });
  assert.equal(only.conflict, false, "只有一个信号谈不上冲突");
  assert.ok(only.confidence < CONFIRM_BELOW_CONFIDENCE);
  assert.equal(shouldAskConfirmation({ merged: only, firstReplyDelivered: true }), true);
});

test("AC-014 浏览器单独说话不问——那是设备自己的设置，通常就是对的", () => {
  const browser = mergeLocationSignals([sig("browser_iana", "Australia/Sydney")], { at: AT });
  assert.ok(browser.confidence >= CONFIRM_BELOW_CONFIDENCE);
  assert.equal(shouldAskConfirmation({ merged: browser, firstReplyDelivered: true }), false);
});

test("AC-014 墙上时间相同的两个时区不算冲突", () => {
  // 按字符串比的话，一个在重庆的人会被问「你到底在上海还是重庆」——两个答案
  // 对他毫无区别。
  const same = mergeLocationSignals([
    sig("browser_iana", "Asia/Chongqing"),
    sig("cloudflare_timezone", "Asia/Shanghai"),
  ], { at: AT });
  assert.equal(same.conflict, false, "同一个墙上时间被判成了冲突");
  assert.equal(shouldAskConfirmation({ merged: same, firstReplyDelivered: true }), false);
  assert.equal(sameWallClock("Asia/Chongqing", "Asia/Shanghai", AT), true);
  // 乌鲁木齐是 UTC+6，墙上时间和北京**不同**——不能因为「也在中国」就放过。
  assert.equal(sameWallClock("Asia/Urumqi", "Asia/Shanghai", AT), false);
});

test("AC-014 用户自己说过的，永远不问", () => {
  const explicit = mergeLocationSignals([
    sig("explicit_user", "Asia/Tokyo"),
    sig("cloudflare_timezone", "Pacific/Auckland"),
  ], { at: AT });
  assert.equal(explicit.conflict, true, "冲突还是要标出来");
  assert.equal(shouldAskConfirmation({ merged: explicit, firstReplyDelivered: true }), false,
    "他自己说了还去问他，是在质疑用户");
});

// ── AC-014 三：首条回复之后 ────────────────────────────────

test("AC-014 首条成功回复之前不问", () => {
  const conflict = mergeLocationSignals([
    sig("browser_iana", "Australia/Sydney"), sig("cloudflare_timezone", "Pacific/Auckland"),
  ], { at: AT });
  assert.equal(shouldAskConfirmation({ merged: conflict, firstReplyDelivered: false }), false);
  assert.equal(shouldAskConfirmation({ merged: conflict, firstReplyDelivered: true }), true);
});

// ── AC-014 四：只问一次 ────────────────────────────────────

test("AC-014 问过一次就不再问", () => {
  const conflict = mergeLocationSignals([
    sig("browser_iana", "Australia/Sydney"), sig("cloudflare_timezone", "Pacific/Auckland"),
  ], { at: AT });
  const asked = {
    confirmed: false,
    confirmation_asked_at_utc: "2026-07-29T14:00:00.000Z",
    confirmation_asked_timezone: "Australia/Sydney",
  };
  assert.equal(shouldAskConfirmation({ merged: conflict, profile: asked, firstReplyDelivered: true }),
    false, "同一个地方问了第二遍");
});

test("AC-014 换了个地方可以再问一次", () => {
  // 出差到东京是新情况，值得再问；同一个地方问第二遍才是骚扰。
  const now = mergeLocationSignals([
    sig("browser_iana", "Asia/Tokyo"), sig("cloudflare_timezone", "Pacific/Auckland"),
  ], { at: AT });
  const askedAboutSydney = {
    confirmed: false,
    confirmation_asked_at_utc: "2026-07-29T14:00:00.000Z",
    confirmation_asked_timezone: "Australia/Sydney",
  };
  assert.equal(shouldAskConfirmation({ merged: now, profile: askedAboutSydney, firstReplyDelivered: true }),
    true);
});

test("AC-014 已确认过的人不问，哪怕新信号跟他说的不一样", () => {
  const conflict = mergeLocationSignals([
    sig("browser_iana", "Australia/Sydney"), sig("cloudflare_timezone", "Pacific/Auckland"),
  ], { at: AT });
  assert.equal(shouldAskConfirmation({
    merged: conflict, profile: { confirmed: true }, firstReplyDelivered: true,
  }), false);
});

test("AC-014 那句话是一句中文，给了默认，且不要求按格式回复", () => {
  const merged = mergeLocationSignals([sig("browser_iana", "Australia/Sydney", { city: "Sydney" })], { at: AT });
  const question = buildConfirmationQuestion(merged);
  assert.match(question, /Sydney/);
  assert.match(question, /[?？]/, "问句总得有个问号");
  // 不能变成 IVR：「回复 1 确认」在微信聊天里是错的交互。
  assert.ok(!/回复\s*[1１]/.test(question), "把聊天做成了按键菜单");
  assert.ok(question.length <= 120, `太长了：${question.length} 字`);
  // 没有城市时退到时区名的尾巴，不能出现整个 IANA 串。
  const noCity = buildConfirmationQuestion(mergeLocationSignals([sig("browser_iana", "Australia/Sydney")], { at: AT }));
  assert.ok(!noCity.includes("Australia/"), "把 IANA 时区串念给用户听了");
});

// ── AC-013 隐私最小化 ──────────────────────────────────────

test("AC-013 出库投影只放白名单里的字段", () => {
  const profile = {
    user_id: "usr_" + "a".repeat(24),
    timezone: "Australia/Sydney",
    coarse_city: "Sydney",
    coarse_country: "AU",
    source: "browser_iana",
    confidence: 0.8,
    confirmed: false,
    consent_scope: "timezone_only",
    observed_at_utc: "2026-07-29T14:48:00.000Z",
    confirmation_asked_at_utc: "2026-07-29T14:50:00.000Z",
  };
  const projected = publicProjection(profile);
  assert.deepEqual(Object.keys(projected).sort(), [...PUBLIC_FIELDS].sort());
  // user_id 不出去：Timeline 和 Status 是要给人看的，那里不需要内部标识。
  assert.ok(!("user_id" in projected));
  assert.ok(!("consent_scope" in projected));
  assert.ok(Object.isFrozen(projected));
});

test("AC-013 投影的输入里混进精确字段，直接抛而不是挑着放出去", () => {
  assert.throws(
    () => publicProjection({ timezone: "Asia/Tokyo", latitude: 35.6 }),
    /forbidden precise location field/,
  );
});

// ── AC-013 结构面：真库跑真迁移 ────────────────────────────

function realDatabase(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-220-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const db = new DatabaseSync(path.join(dir, "t.db"));
  // 按 MIGRATIONS 的真实顺序跑真实的迁移文件，不自己编 schema。
  // 编出来的 schema 会让测试证明一件没发生的事——CB9-140 上已经栽过一次。
  for (const migration of MIGRATIONS) {
    const sql = fs.readFileSync(path.join(__dirname, "..", "migrations", migration.name), "utf8")
      .replaceAll(/__MIGRATION_\d+_CHECKSUM__/g, "fixture");
    db.exec(sql);
  }
  return db;
}

test("AC-013 迁移 017 之后，位置表里依然没有任何精确定位列", () => {
  // 017 是往这张表上加列的。加列的那一刻正是最容易顺手加上 latitude 的时候，
  // 所以在 016 的守卫之外，这里对**跑完全部迁移之后**的真实表结构再查一遍。
  const db = realDatabase({ after: () => {} });
  const cols = db.prepare("PRAGMA table_info(user_location_profiles_v009)").all().map((c) => c.name);
  const FORBIDDEN = /^(raw_ip|ip|ip_address|latitude|lat|longitude|lng|lon|precise_address|street|postal_code|geohash)$/i;
  assert.deepEqual(cols.filter((c) => FORBIDDEN.test(c)), []);
  // 017 加的三列都在。
  for (const need of ["confirmation_asked_at_utc", "confirmation_asked_at_beijing", "confirmation_asked_timezone"]) {
    assert.ok(cols.includes(need), `017 没生效：缺 ${need}`);
  }
  db.close();
});

test("AC-013 017 是 additive 的——016 建的东西一样不少", () => {
  const sql = fs.readFileSync(
    path.join(__dirname, "..", "migrations", "017_location_confirmation_state.sql"), "utf8",
  );
  assert.ok(!/DROP\s+(TABLE|COLUMN|INDEX)/i.test(sql), "017 里有 DROP");
  assert.ok(!/ALTER\s+TABLE\s+\S+\s+RENAME/i.test(sql), "017 里有 RENAME");
  // 只允许 ADD COLUMN 形式的 ALTER。
  for (const alter of sql.match(/ALTER TABLE[\s\S]*?;/gi) || []) {
    assert.match(alter, /ADD COLUMN/i, `非 ADD COLUMN 的 ALTER：${alter.slice(0, 60)}`);
  }
});

test("017 已在 MIGRATIONS 里注册——漏了它永远不会被执行", () => {
  const entry = MIGRATIONS.find((m) => m.name === "017_location_confirmation_state.sql");
  assert.ok(entry, "017 没注册：文件在、语法对，但永远不跑，而单测全绿");
  assert.equal(entry.version, 15);
  assert.equal(entry.version, MIGRATIONS.length, "版本号和数组长度对不上");
});
