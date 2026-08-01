"use strict";

// CB9-220 位置画像的**落库层与整条绑定链路**（AC-013 / AC-014 / AC-015 的落库面）
//
// 上一份验的是合并和判定这些纯函数。这一份验它们有没有真的接上库：用真实的
// RuntimeSpoolDatabase 写读删，并且把「加入页采到 → 扫码确认 → 第一句话」这三
// 跳串起来跑一遍。
//
// 中间那一跳最容易断：观测是在加入页按 **ticket** 采的，那时候这个人还不存在；
// 扫码确认的瞬间票就被删了。少了改键这一步，观测跟着票一起消失——采了等于没采，
// 而所有纯函数测试照样全绿。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const {
  PendingTimezoneSignals,
  safeObservation,
} = require("../src/services/location/timezone-signals");

const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;

function openDatabase(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-220-store-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const database = new RuntimeSpoolDatabase({
    databasePath: path.join(dir, "spool.db"),
    encryptionKey: Buffer.alloc(32, 7),
  });
  t.after(() => { try { database.close(); } catch { /* 已经关了 */ } });
  return database;
}

test("AC-013 写进去再读出来，没有任何精确定位字段", (t) => {
  const database = openDatabase(t);
  const saved = database.upsertUserLocationProfile({
    userId: ALICE,
    timezone: "Australia/Sydney",
    city: "Sydney",
    country: "AU",
    source: "browser_iana",
    confidence: 0.8,
  });
  assert.equal(saved.timezone, "Australia/Sydney");
  assert.equal(saved.coarse_city, "Sydney");
  assert.equal(saved.confirmed, false);
  const dumped = JSON.stringify(saved);
  for (const forbidden of ["latitude", "longitude", "raw_ip", "203.0.113"]) {
    assert.ok(!dumped.includes(forbidden), `读回来的画像里有 ${forbidden}`);
  }
});

test("AC-013 库层再挡一次非法来源和非法时区——绕过采集层直接写也过不去", (t) => {
  const database = openDatabase(t);
  assert.throws(() => database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Australia/Sydney", source: "guessed", confidence: 1,
  }), /LOCATION_SOURCE_INVALID/);
  assert.throws(() => database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Mars/Olympus", source: "browser_iana", confidence: 1,
  }), /LOCATION_TIMEZONE_INVALID/);
  assert.throws(() => database.upsertUserLocationProfile({
    userId: "不是合法 user_id", timezone: "Asia/Tokyo", source: "browser_iana", confidence: 1,
  }), /USER_ID_REQUIRED/);
});

test("AC-014 用户亲口确认过的，不会被推断信号盖掉", (t) => {
  // 少了这条：一个在东京出差的人说完「我在东京」之后，下次打开加入页或者换个
  // 网络，浏览器/CF 的信号就把他改回去了——而他并没有再说过什么。
  const database = openDatabase(t);
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Asia/Tokyo", source: "explicit_user",
    confidence: 1, confirmed: true,
  });
  const afterInference = database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Australia/Sydney", source: "browser_iana", confidence: 0.8,
  });
  assert.equal(afterInference.timezone, "Asia/Tokyo", "推断信号盖掉了用户亲口说的");
  assert.equal(afterInference.confirmed, true);
  // 但他自己再说一次是可以改的。
  const afterUser = database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Europe/Paris", source: "explicit_user",
    confidence: 1, confirmed: true,
  });
  assert.equal(afterUser.timezone, "Europe/Paris");
});

test("AC-014 markLocationConfirmationAsked 把两个时间列成对写上", (t) => {
  const database = openDatabase(t);
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Australia/Sydney", source: "cloudflare_timezone", confidence: 0.4,
  });
  const asked = database.markLocationConfirmationAsked({
    userId: ALICE,
    timezone: "Australia/Sydney",
    now: Date.parse("2026-07-29T14:48:00.000Z"),
  });
  assert.equal(asked.confirmation_asked_at_utc, "2026-07-29T14:48:00.000Z");
  // 北京时间那一列不是摆设：只写 UTC 的话，给人看的时间要么是错的、要么得在
  // 每个读的地方各转一次——而总有一处会忘。
  assert.equal(asked.confirmation_asked_at_beijing, "2026-07-29 22:48:00");
  assert.equal(asked.confirmation_asked_timezone, "Australia/Sydney");
});

test("AC-015 删掉之后读回来是 null——不是标记成隐藏", (t) => {
  const database = openDatabase(t);
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Asia/Tokyo", source: "browser_iana", confidence: 0.8,
  });
  assert.ok(database.readUserLocationProfile(ALICE));
  assert.equal(database.deleteUserLocationProfile(ALICE), true);
  assert.equal(database.readUserLocationProfile(ALICE), null, "「派生位置不可再读」没做到");
  // 删一个不存在的返回 false，不抛。
  assert.equal(database.deleteUserLocationProfile(ALICE), false);
});

test("跨用户隔离：A 的位置读不到 B 的", (t) => {
  const database = openDatabase(t);
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Australia/Sydney", source: "browser_iana", confidence: 0.8,
  });
  database.upsertUserLocationProfile({
    userId: BOB, timezone: "America/New_York", source: "browser_iana", confidence: 0.8,
  });
  assert.equal(database.readUserLocationProfile(ALICE).timezone, "Australia/Sydney");
  assert.equal(database.readUserLocationProfile(BOB).timezone, "America/New_York");
  // 删 A 不影响 B。
  database.deleteUserLocationProfile(ALICE);
  assert.equal(database.readUserLocationProfile(BOB).timezone, "America/New_York");
});

test("一个人只有一行——同一个人写两次是更新不是新增", (t) => {
  const database = openDatabase(t);
  for (const zone of ["Asia/Tokyo", "Australia/Sydney", "Europe/Paris"]) {
    database.upsertUserLocationProfile({
      userId: ALICE, timezone: zone, source: "browser_iana", confidence: 0.8,
    });
  }
  const rows = database.database
    .prepare("SELECT COUNT(*) AS n FROM user_location_profiles_v009 WHERE user_id=?")
    .get(ALICE);
  assert.equal(rows.n, 1, `同一个人有 ${rows.n} 行位置画像`);
  assert.equal(database.readUserLocationProfile(ALICE).timezone, "Europe/Paris");
});

// ── 三跳绑定链路 ────────────────────────────────────────────

test("AC-014 加入页 → 扫码确认 → 第一句话，观测三跳都不掉", () => {
  const pending = new PendingTimezoneSignals();
  const observation = safeObservation({
    source: "browser_iana", timezone: "Australia/Sydney", city: "Sydney", country: "AU",
  });

  // 一跳：加入页按 ticket 采集。这时候这个人还不存在。
  assert.equal(pending.record("qr-ticket-1", observation), true);

  // 二跳：扫码确认，iLink 给他建了账号，票马上要被删——先改键。
  assert.equal(pending.rekey("qr-ticket-1", "acct-1"), true);
  assert.equal(pending.take("qr-ticket-1"), null, "改键后旧票不该还能取到");

  // 三跳：他说第一句话，这时候才有 user_id。
  const bound = pending.take("acct-1");
  assert.ok(bound, "观测在中间某一跳掉了——采了等于没采");
  assert.equal(bound.timezone, "Australia/Sydney");
});

test("改键不存在的票是 no-op，不会凭空造一条观测", () => {
  const pending = new PendingTimezoneSignals();
  assert.equal(pending.rekey("没这张票", "acct-1"), false);
  assert.equal(pending.take("acct-1"), null);
  assert.equal(pending.size, 0);
});

test("两个人同时在扫码，各自的观测不会串", () => {
  const pending = new PendingTimezoneSignals();
  pending.record("t-a", safeObservation({ source: "browser_iana", timezone: "Australia/Sydney" }));
  pending.record("t-b", safeObservation({ source: "browser_iana", timezone: "America/New_York" }));
  pending.rekey("t-a", "acct-a");
  pending.rekey("t-b", "acct-b");
  assert.equal(pending.take("acct-a").timezone, "Australia/Sydney");
  assert.equal(pending.take("acct-b").timezone, "America/New_York");
});
