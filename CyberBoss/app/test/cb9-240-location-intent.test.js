"use strict";

// CB9-240 用大白话纠正、切换和删除位置（AC-015）
//
//   AC-015 发送纠正、切换和删除语句；时区即时更新，删除后回退且派生位置不可
//          再读。
//
// 这三件必须是**确定性口令**，不能交给模型。理由和提醒那条完全一样：模型可能
// 调工具，也可能只是回一句「好的」然后什么都没改——而用户以为改好了，接下来
// 所有的时间都按错的时区算，一直到他自己发现为止。
//
// 反面同样重要：「我在想东京的事」不能被听成一次搬家。误判的代价比漏判大得多
// ——漏判只是交给模型，误判是把这个人的时区改错了还告诉他「记下了」。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  CITY_ZONES,
  buildForgetReply,
  buildSetReply,
  buildWhereReply,
  parseLocationIntent,
} = require("../src/services/location/location-intent");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { isValidIanaZone } = require("../src/services/time/canonical-time");

const ALICE = `usr_${"a".repeat(24)}`;

// ── 纠正与切换 ─────────────────────────────────────────────

test("AC-015 纠正：「不是，我在悉尼」", () => {
  for (const text of ["不是，我在悉尼", "不对，我在悉尼", "其实我在悉尼", "我在悉尼"]) {
    const intent = parseLocationIntent(text);
    assert.ok(intent, `没认出来：${text}`);
    assert.equal(intent.kind, "set");
    assert.equal(intent.timezone, "Australia/Sydney");
    assert.equal(intent.city, "悉尼");
  }
});

test("AC-015 切换：「我到纽约了」「我回北京了」", () => {
  const toNewYork = parseLocationIntent("我到纽约了");
  assert.equal(toNewYork?.timezone, "America/New_York");
  const backToBeijing = parseLocationIntent("我回北京了");
  assert.equal(backToBeijing?.timezone, "Asia/Shanghai");
  assert.equal(parseLocationIntent("我搬到墨尔本了")?.timezone, "Australia/Melbourne");
  assert.equal(parseLocationIntent("我现在在东京")?.timezone, "Asia/Tokyo");
  assert.equal(parseLocationIntent("我飞到伦敦了")?.timezone, "Europe/London");
});

test("AC-015 删除：「别记我的位置」", () => {
  for (const text of ["别记我的位置", "别记我在哪", "忘掉我在哪", "忘掉我的位置", "删掉我的位置"]) {
    assert.equal(parseLocationIntent(text)?.kind, "forget", `没认出来：${text}`);
  }
});

test("AC-015 删除要先判——「别记我在哪」里也有「我在」两个字", () => {
  // 先判纠正的话，这句会被当成「他在『哪』这个城市」。顺序不是随便排的。
  const intent = parseLocationIntent("别记我在哪");
  assert.equal(intent?.kind, "forget", "一句删除被听成了一次搬家");
});

test("AC-015 查询：「我在哪」不是修改", () => {
  for (const text of ["我在哪", "我现在在哪儿", "你知道我在哪吗".replace("吗", ""), "我的时区是什么"]) {
    const intent = parseLocationIntent(text);
    assert.equal(intent?.kind, "where", `没认出来：${text}`);
  }
});

// ── 反面：不能误判 ─────────────────────────────────────────

test("AC-015 长句子里提到城市不算搬家", () => {
  const NOT_A_MOVE = [
    "我在想东京的事",
    "我在东京的朋友说那边下雨了",
    "帮我查一下悉尼现在几点",
    "纽约的会议改到明天了",
    "我在看一本关于伦敦的书",
    "提醒我明天给北京的同事打电话",
  ];
  for (const text of NOT_A_MOVE) {
    assert.equal(parseLocationIntent(text), null, `误判成了改位置：${text}`);
  }
});

test("AC-015 太长的句子一律不接", () => {
  const long = `我在东京${"，".repeat(40)}`;
  assert.equal(parseLocationIntent(long), null);
});

test("AC-015 长度上限挡的是空白填充——正则的 \\s* 能吃掉任意长空白", () => {
  // 这条是变异测试补出来的：把上限从 40 放到 4000，原来那批测试**全绿**。
  // 因为它们靠的是行首行尾锚，而锚挡不住这个——`我在` + 一百个空格 + `东京`
  // 完全符合 ^prefix city suffix$，只是长。
  const padded = `我在${" ".repeat(100)}东京`;
  assert.ok(padded.length > 40);
  assert.equal(parseLocationIntent(padded), null, "空白填充绕过了长度上限");
  // 反面：正常长度的同样写法要认。
  assert.equal(parseLocationIntent("我在 东京")?.timezone, "Asia/Tokyo");
});

test("AC-015 城市正则是预编译的，不是每条消息现建 50 个", () => {
  // 每条入站消息都会走 matchPlace。现建 50 个 RegExp 是纯浪费，长输入上更贵。
  const fs2 = require("node:fs");
  const src = fs2.readFileSync(
    require("node:path").join(__dirname, "..", "src", "services", "location", "location-intent.js"),
    "utf8",
  );
  assert.ok(!/function matchPlace[\s\S]*?new RegExp/.test(src),
    "matchPlace 里还在现建正则");
  assert.match(src, /const CITY_PATTERNS = Object\.freeze/);
});

test("AC-015 认不出来的城市返回 null，不猜", () => {
  // 猜的代价是把时区改错了还告诉他「记下了」。
  assert.equal(parseLocationIntent("我在瓦加杜古"), null);
  assert.equal(parseLocationIntent("我在火星"), null);
  assert.equal(parseLocationIntent(""), null);
  assert.equal(parseLocationIntent(null), null);
});

test("城市表里每一个时区都是合法的 IANA 名字", () => {
  // 打错一个字母的后果是这个城市永远改不了时区，而且只有那个城市的人会中招。
  const bad = Object.entries(CITY_ZONES).filter(([, zone]) => !isValidIanaZone(zone));
  assert.deepEqual(bad, [], `这些时区名不合法：${JSON.stringify(bad)}`);
});

test("直接说 IANA 时区名的后门", () => {
  // 给会用的人留的，不出现在任何提示里——新手路径不能有技术术语。
  assert.equal(parseLocationIntent("我的时区是 Asia/Tokyo")?.timezone, "Asia/Tokyo");
  assert.equal(parseLocationIntent("我的时区改成 America/New_York")?.timezone, "America/New_York");
  // 编的时区名不接。
  assert.equal(parseLocationIntent("我的时区是 Mars/Olympus"), null);
});

// ── 文案 ───────────────────────────────────────────────────

test("AC-015 改完那句话说清楚改成了什么，以及怎么撤销", () => {
  const reply = buildSetReply({ city: "悉尼", timezone: "Australia/Sydney" });
  assert.match(reply, /悉尼/);
  // 「改错了怎么办」是用户在这一刻唯一会想的问题。
  assert.match(reply, /别记我的位置/, "没告诉他怎么撤销");
  // 不能把 IANA 时区串念给用户听。
  assert.ok(!reply.includes("Australia/"), "把技术标识吐给用户了");
});

test("AC-015 删完那句话说清楚回退到什么", () => {
  const reply = buildForgetReply();
  assert.match(reply, /删掉/);
  assert.match(reply, /北京时间/, "没说回退到哪个口径");
});

test("AC-015 查询的回答区分「他说的」和「我猜的」", () => {
  assert.match(buildWhereReply(null), /没记/);
  const guessed = buildWhereReply({ coarse_city: "悉尼", timezone: "Australia/Sydney", confirmed: false });
  assert.match(guessed, /猜/, "把推断说成了确定");
  const stated = buildWhereReply({ coarse_city: "悉尼", timezone: "Australia/Sydney", confirmed: true });
  assert.match(stated, /你跟我说过/);
  assert.ok(!stated.includes("猜"), "他自己说的还说是猜的");
});

// ── 落库：即时更新 + 删除后不可再读 ───────────────────────

function openDatabase(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-240-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const database = new RuntimeSpoolDatabase({
    databasePath: path.join(dir, "spool.db"),
    encryptionKey: Buffer.alloc(32, 9),
  });
  t.after(() => { try { database.close(); } catch { /* 已经关了 */ } });
  return database;
}

test("AC-015 说完就生效——不用等下一轮，也不用重启", (t) => {
  const database = openDatabase(t);
  const intent = parseLocationIntent("我到纽约了");
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: intent.timezone, city: intent.city,
    source: "explicit_user", confidence: 1, confirmed: true, consentScope: "user_stated",
  });
  const profile = database.readUserLocationProfile(ALICE);
  assert.equal(profile.timezone, "America/New_York");
  assert.equal(profile.confirmed, true);
  assert.equal(profile.source, "explicit_user");
});

test("AC-015 他说过之后，推断信号再也盖不掉", (t) => {
  // confirmed 这一位是**保护**。少了它，他说完「我在东京」之后，下次打开加入页
  // 或者换个网络就被浏览器/Cloudflare 的信号改回去了——而他并没有再说过什么。
  const database = openDatabase(t);
  const intent = parseLocationIntent("我在东京");
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: intent.timezone, city: intent.city,
    source: "explicit_user", confidence: 1, confirmed: true, consentScope: "user_stated",
  });
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Australia/Sydney", source: "browser_iana", confidence: 0.8,
  });
  assert.equal(database.readUserLocationProfile(ALICE).timezone, "Asia/Tokyo");
  // 但他自己再说一次能改。
  const again = parseLocationIntent("我回北京了");
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: again.timezone, city: again.city,
    source: "explicit_user", confidence: 1, confirmed: true, consentScope: "user_stated",
  });
  assert.equal(database.readUserLocationProfile(ALICE).timezone, "Asia/Shanghai");
});

test("AC-015 删除之后派生位置不可再读，且回退北京时间", (t) => {
  const database = openDatabase(t);
  database.upsertUserLocationProfile({
    userId: ALICE, timezone: "Asia/Tokyo", city: "东京",
    source: "explicit_user", confidence: 1, confirmed: true, consentScope: "user_stated",
  });
  assert.ok(database.readUserLocationProfile(ALICE));

  assert.equal(parseLocationIntent("别记我的位置").kind, "forget");
  database.deleteUserLocationProfile(ALICE);

  assert.equal(database.readUserLocationProfile(ALICE), null,
    "删了还读得到——「派生位置不可再读」没做到");
  // 表里一行都不剩，不是标记成隐藏。
  const rows = database.database
    .prepare("SELECT COUNT(*) AS n FROM user_location_profiles_v009 WHERE user_id=?")
    .get(ALICE);
  assert.equal(rows.n, 0);
  // 删完之后回答的是「没记」，不是上一次那个地方。
  assert.match(buildWhereReply(database.readUserLocationProfile(ALICE)), /没记/);
});

test("AC-015 删除只删自己的——不影响别人", (t) => {
  const database = openDatabase(t);
  const BOB = `usr_${"b".repeat(24)}`;
  for (const [id, zone] of [[ALICE, "Asia/Tokyo"], [BOB, "Australia/Sydney"]]) {
    database.upsertUserLocationProfile({
      userId: id, timezone: zone, source: "explicit_user",
      confidence: 1, confirmed: true, consentScope: "user_stated",
    });
  }
  database.deleteUserLocationProfile(ALICE);
  assert.equal(database.readUserLocationProfile(ALICE), null);
  assert.equal(database.readUserLocationProfile(BOB)?.timezone, "Australia/Sydney");
});

// ── 接线：这条路真的挂在确定性口令链上了 ───────────────────

test("AC-015 handleLocationCommand 真的挂在口令链上", () => {
  // 这个仓的招牌坏法：解析器写好了、单测全绿、没人调用。
  const src = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  assert.match(src, /this\.handleLocationCommand\(normalized, userId\)/,
    "解析器写好了但没挂上——线上说「我在东京」不会有任何反应");
  assert.match(src, /handleLocationCommand\(normalized, userId\) \{/);
  // 而且要在 admissionHandledBeforeJob 那一段里，和提醒/待办同一层。
  const block = src.slice(
    src.indexOf('if (["owner", "user"].includes(decision.route)'),
    src.indexOf("// 普通用户在这里就办完"),
  );
  assert.ok(block.includes("handleLocationCommand"), "挂在了别的地方，不在口令链上");
});

test("AC-015 用户自己说的一律 explicit_user + confirmed", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const handler = src.slice(
    src.indexOf("handleLocationCommand(normalized, userId) {"),
    src.indexOf("senderTimezone(normalized) {"),
  );
  assert.match(handler, /source: "explicit_user"/);
  assert.match(handler, /confirmed: true/);
  assert.match(handler, /confidence: 1/);
  // 删除走的是真删，不是把 confidence 改成 0。
  assert.match(handler, /deleteUserLocationProfile\(userId\)/);
});
