"use strict";

// 每个人自己的语气。
//
// 迁移 010 的注释里写着「全机一份语气，不按用户分」。那句话在只有主人一个人
// 用的时候是对的。现在每个人扫码绑自己的微信、各有各的号，同一个腔调对所有人
// 就不成立了。
//
// 模型是：**主人那一行是默认值**，谁给自己设过就用自己那一行。
// 这条测试要守住的三件事：
//   一、没设过的人沿用主人的默认值（不是掉回出厂设置）；
//   二、设过的人不受主人改默认值影响（否则「自己的语气」就是假的）；
//   三、A 的语气永远不会漏给 B——这是隔离，不是偏好。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  PersonaStore,
  mergePersonaForPerson,
  normalizePersonPersona,
  renderPersonaInstruction,
} = require("../src/services/persona/persona-store");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");

const ENCRYPTION_KEY = Buffer.alloc(32, 71);
const IDENTITY_KEY = Buffer.alloc(32, 73);
// user_id 的形状由 USER_ID_PATTERN 定死：usr_ 加 20~64 个字符。
const ALICE = `usr_${"a".repeat(24)}`;
const BOB = `usr_${"b".repeat(24)}`;

function openStore(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-user-persona-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const database = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => database.close());
  return { database, store: new PersonaStore({ database }) };
}

// ── 默认值继承 ──────────────────────────────────────────────

test("没给自己设过语气的人，沿用主人那一行——不是掉回出厂设置", (t) => {
  const { store } = openStore(t);
  store.write({ tone: "quiet", length: "short", note: "夜里说话轻一点" });

  const inherited = store.readFor(ALICE);

  assert.equal(inherited.tone, "quiet");
  assert.equal(inherited.length, "short");
  assert.equal(inherited.note, "夜里说话轻一点");
  assert.equal(store.hasOwnPersona(ALICE), false);
});

test("设过之后就用自己那一套，主人再改默认值也不动他", (t) => {
  const { store } = openStore(t);
  store.write({ tone: "quiet", length: "short", note: "夜里说话轻一点" });
  store.writeFor(ALICE, { tone: "warm", length: "long", callMe: "小林" });

  // 主人换了默认值。
  store.write({ tone: "plain", length: "short", note: "全部简短" });

  const alice = store.readFor(ALICE);
  assert.equal(alice.tone, "warm", "主人改默认值把这个人自己设的覆盖掉了");
  assert.equal(alice.length, "long");
  assert.equal(alice.callMe, "小林");
  assert.equal(store.hasOwnPersona(ALICE), true);

  // 没设过的人跟着新默认值走。
  assert.equal(store.readFor(BOB).tone, "plain");
});

test("整份覆盖，不逐字段——分不清「没设过」和「设成了关」的东西不能猜", (t) => {
  const { store } = openStore(t);
  store.write({ tone: "warm", emoji: true, callMe: "老板", note: "记得提醒我喝水" });
  // 这个人只挑了语气，别的都没填。
  store.writeFor(ALICE, { tone: "quiet" });

  const alice = store.readFor(ALICE);
  assert.equal(alice.tone, "quiet");
  // emoji / callMe / note 跟着他自己那一份走（都是默认值），不会把主人的
  // "老板"和"记得提醒我喝水"混进来——那才是真正会串人的做法。
  assert.equal(alice.emoji, false);
  assert.equal(alice.callMe, "");
  assert.equal(alice.note, "");
});

// ── 隔离 ────────────────────────────────────────────────────

test("A 的语气一个字都不会漏给 B", (t) => {
  const { store } = openStore(t);
  store.writeFor(ALICE, { tone: "warm", callMe: "只有 A 能看到的称呼", note: "A 的私事" });
  store.writeFor(BOB, { tone: "plain", callMe: "B" });

  const bob = store.readFor(BOB);
  const rendered = renderPersonaInstruction(bob);

  assert.ok(!rendered.includes("只有 A 能看到的称呼"));
  assert.ok(!rendered.includes("A 的私事"));
  assert.match(rendered, /- 称呼对方为「B」。/);
});

test("换到别人的行上解不开——AAD 里带着 user_id，不是靠上层记得筛", (t) => {
  const { database, store } = openStore(t);
  store.writeFor(ALICE, { tone: "warm", callMe: "A" });

  // 把 A 的密文原样搬到 B 那一行。这是"上层筛漏了"的最坏情况。
  const row = database.database
    .prepare("SELECT payload_ciphertext, payload_sha256, updated_at FROM user_persona WHERE user_id=?")
    .get(ALICE);
  database.database
    .prepare(`INSERT INTO user_persona(user_id, payload_ciphertext, payload_sha256, updated_at)
              VALUES (?, ?, ?, ?)`)
    .run(BOB, row.payload_ciphertext, row.payload_sha256, row.updated_at);

  assert.throws(() => database.readUserPersona(BOB));
  // 上层不该因此崩：读不出来就退回主人那一行。
  assert.equal(store.readFor(BOB).callMe, "");
});

// ── 主动打招呼和名额永远只属于主人 ──────────────────────────

// 「每个用户的设置应该都是个人的，比如主动找我这个权限⋯应该是在用户下每个人
//   都能单独保存。」
//
// 这一条原来是反过来断言的：proactive 写进个人那一行也不生效，理由是「唤醒模型
// 只对 owner 开放」。那条边界在当时成立——那时候访客的消息根本走不到模型。但
// 后来普通用户有了自己的模型路径（runUserModelTurn），前 N 个人还共用主人那把
// 钥匙，那个前提早就没了。所以断言跟着改。
//
// access 没跟着改：它是整台机器的开门规则，不是某个人的属性。一个访客能把自己
// 那一行的 seats 改成 999 的话，名额就不是名额了。

test("每个人的「主动找我」是他自己的，谁也不影响谁", (t) => {
  const { store } = openStore(t);
  store.write({
    proactive: { enabled: true, minMinutes: 60, maxMinutes: 90, quietStart: 1, quietEnd: 6 },
  });
  store.writeFor(ALICE, {
    tone: "quiet",
    proactive: { enabled: false, minMinutes: 120, maxMinutes: 240, quietStart: 0, quietEnd: 8 },
  });

  const alice = store.readFor(ALICE);
  assert.equal(alice.proactive.enabled, false, "他关掉了，就该是关的");
  assert.equal(alice.proactive.minMinutes, 120);
  // 主人那一行没被动过。
  assert.equal(store.read().proactive.enabled, true);
  assert.equal(store.read().proactive.minMinutes, 60);
});

test("没给自己设过的人，沿用主人那一份当默认", (t) => {
  const { store } = openStore(t);
  store.write({
    proactive: { enabled: true, minMinutes: 45, maxMinutes: 240, quietStart: 23, quietEnd: 8 },
  });
  store.writeFor(ALICE, { tone: "quiet" });

  assert.equal(store.readFor(ALICE).proactive.minMinutes, 45);
});

test("名额仍然不是个人属性——访客改不动整台机器的开门规则", (t) => {
  const { store } = openStore(t);
  store.write({ access: { mode: "open", seats: 3 } });
  store.writeFor(ALICE, { tone: "quiet", access: { mode: "open", seats: 999 } });

  assert.equal(store.readFor(ALICE).access.seats, 3);
  assert.deepEqual(
    Object.keys(normalizePersonPersona({ tone: "quiet", proactive: {}, access: {} })).sort(),
    ["callMe", "emoji", "length", "note", "proactive", "tone", "updatedAt"],
  );
});

// ── 退化路径：坏了也不能让消息发不出去 ──────────────────────

test("库不支持按人存的时候退回主人那一行，而不是抛错", () => {
  const store = new PersonaStore({ database: { readOwnerPersona: () => null } });
  assert.equal(store.readFor(ALICE).tone, store.read().tone);
  assert.equal(store.hasOwnPersona(ALICE), false);
});

test("空 userId 直接退回主人那一行；写空 userId 是明确的错", (t) => {
  const { store } = openStore(t);
  store.write({ tone: "quiet" });

  assert.equal(store.readFor("").tone, "quiet");
  assert.throws(() => store.writeFor("", { tone: "warm" }), /PERSONA_USER_REQUIRED/);
});

test("mergePersonaForPerson 不给个人那份时原样返回主人那份", () => {
  const owner = { tone: "warm", length: "long", callMe: "老板" };
  const merged = mergePersonaForPerson(owner, null);
  assert.equal(merged.tone, "warm");
  assert.equal(merged.callMe, "老板");
});

// ── 真实链路 ────────────────────────────────────────────────

test("语气按人读这件事在 buildRuntimeTurn 里是真的，不是只写在存储层", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  assert.match(source, /resolveUserIdForPersona\(prepared\)/);
  assert.match(source, /currentPersonaInstruction\(userId\s*=\s*""\)/);
  // readFor 必须真的被调用；只加一个方法不接线等于没做。
  assert.match(source, /this\.personaStore\.readFor\(userId\)/);
});

test("后台那一栏是真接上的：按人读、按人存、并说清是自己设的还是沿用默认", () => {
  const page = fs.readFileSync(path.join(__dirname, "../templates/dashboard.html"), "utf8");
  // 读要带 person，否则打开谁都显示主人那一行。
  assert.match(page, /\/admin\/api\/persona\?person=/);
  // 存也要带 person，否则「只保存给他」会把所有人的默认值改掉——最坏的一种错。
  assert.match(page, /person:\s*openPerson/);
  // inherited 必须显示出来。
  assert.match(page, /data\.inherited/);
  // 匹配真正的赋值，不匹配注释里提到它的那一行。
  assert.ok(!/\.innerHTML\s*=/.test(page), "后台页里出现了 innerHTML 赋值");

  const portal = fs.readFileSync(path.join(__dirname, "../src/services/portal/portal-server.js"), "utf8");
  assert.match(portal, /adminPersonaRead\(\{\s*\n?\s*person:/);
});

test("迁移 014 是纯新增，且登记在册", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/014_user_persona.sql"), "utf8");
  assert.ok(!/\b(DROP|ALTER)\b/i.test(sql), "迁移里出现了 DROP 或 ALTER");
  assert.match(sql, /CREATE TABLE IF NOT EXISTS user_persona/);
  assert.match(sql, /VALUES \(\s*12,/);

  const adapter = fs.readFileSync(path.join(__dirname, "../src/services/db/database-adapter.js"), "utf8");
  assert.match(adapter, /version: 12,\s*\n\s*name: "014_user_persona\.sql"/);
});
