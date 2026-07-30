"use strict";

// 「boss 要能主动去找每个人，每个人有自己的开关」。
//
// 2026-07-30 主人报的是「boss 现在只能主动来找我」。查下来后端其实早就是按人
// 走的（next-checkin.json 里线上排着 3 个真人），真正断掉的是三处：
//
//   1. 开关默认关，而**除主人外没有任何人能打开它**——/me 那一页从头到尾只有
//      GET，一个写接口都没有。
//   2. 微信里发「别再问我」写的是 user_settings.checkin_enabled，轮询器读的是
//      user_persona.proactive。两张表毫无关系，读前者的 planProactiveMessage
//      还从来没有被调用过。于是那条口令有回复、有落库、零效果。
//   3. 没自己那一行的人，proactive 整份继承主人——主人一关，所有人跟着哑，
//      看起来正好就是「只找主人」。
//
// 这一份钉的是这三条各自的反面，外加一条整链路可达性：这个仓的惯犯是中间层按
// 名字解构漏字段，上层传了、下层没接、测试全绿。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { PersonaStore, PROACTIVE_DEFAULTS } = require("../src/services/persona/persona-store");
const { PortalHttpServer } = require("../src/services/portal/portal-server");
const { UserCompanionTurn } = require("../src/core/user-companion-turn");

const OWNER = `usr_${"o".repeat(24)}`;
const GUEST = `usr_${"g".repeat(24)}`;
const GUEST_TOKEN = `g${"A1_-b2Cd".repeat(5)}xyz`;

const APP_SOURCE = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");

// 内存里的一份 persona 表，够测语义。
function fakeDb() {
  const owner = { value: null };
  const people = new Map();
  return {
    readOwnerPersona: () => (owner.value ? { value: owner.value, updatedAt: "" } : null),
    writeOwnerPersona: (v) => { owner.value = v; },
    readUserPersona: (id) => (people.has(id) ? { value: people.get(id), updatedAt: "" } : null),
    writeUserPersona: (id, v) => { people.set(id, v); },
  };
}

function storeFor() {
  return new PersonaStore({ database: fakeDb(), ownerUserId: () => OWNER });
}

// ── 一、开关是本人的，不跟着主人 ─────────────────────────────

test("主人把自己的主动找我关掉，别人不跟着关", () => {
  const store = storeFor();
  store.write({ proactive: { enabled: false, minMinutes: 10 } });

  assert.equal(store.read().proactive.enabled, false, "主人自己那份要照他说的关掉");
  assert.equal(
    store.readFor(GUEST).proactive.enabled,
    true,
    "别人不该被主人的开关连坐——这正是「只找主人」看起来的样子",
  );
  assert.equal(store.readFor(GUEST).proactive.minMinutes, PROACTIVE_DEFAULTS.minMinutes);
});

test("主人自己那一份读得回来，不会掉进「没设过」的分支", () => {
  const store = storeFor();
  store.write({ proactive: { enabled: false, minMinutes: 77, maxMinutes: 88 } });
  // readFor(主人) 必须等于 read()，否则后台一打开就把他自己的频率显示错。
  assert.deepEqual(store.readFor(OWNER).proactive, store.read().proactive);
  assert.equal(store.readFor(OWNER).proactive.minMinutes, 77);
});

// ── 二、微信口令要写进真的被读的那张表 ───────────────────────

test("发「别再问我」改的是轮询器真正会读的那一份", () => {
  const store = storeFor();
  const writes = [];
  const companion = new UserCompanionTurn({
    database: {
      prepare: () => ({ run: () => {}, get: () => null, all: () => [] }),
    },
    personaStore: {
      setProactiveFor: (userId, patch) => { writes.push({ userId, patch }); },
    },
  });

  const reply = companion.handle({ userId: GUEST, may: () => true }, "别再问我");

  assert.equal(reply.modelCalls, 0, "口令必须零模型调用");
  assert.deepEqual(writes, [{ userId: GUEST, patch: { enabled: false } }]);

  writes.length = 0;
  companion.handle({ userId: GUEST, may: () => true }, "可以问我");
  assert.deepEqual(writes, [{ userId: GUEST, patch: { enabled: true } }]);
  void store;
});

test("口令只改开关，不把这个人的语气一起清掉", () => {
  const store = storeFor();
  store.writeFor(GUEST, { tone: "plain", callMe: "小李", proactive: { enabled: true } });

  store.setProactiveFor(GUEST, { enabled: false });

  assert.equal(store.readFor(GUEST).proactive.enabled, false);
  assert.equal(store.readFor(GUEST).tone, "plain", "口令只知道 enabled，不能整份覆盖");
  assert.equal(store.readFor(GUEST).callMe, "小李");
});

test("app 真的把 personaStore 交给了 UserCompanionTurn", () => {
  // 少了这一行，口令写进去的还是那张没人读的表，而且测试照样全绿。
  const start = APP_SOURCE.indexOf("new UserCompanionTurn({");
  assert.notEqual(start, -1);
  const block = APP_SOURCE.slice(start, APP_SOURCE.indexOf("});", start));
  assert.match(block, /personaStore:\s*this\.personaStore/);
});

// ── 三、/me 那一页真的能改，而且只能改自己的 ─────────────────

function bootApp({ store }) {
  const app = Object.create(CyberbossApp.prototype);
  app.personaStore = store;
  app.adminSessionService = {
    verify: ({ token }) => (token === GUEST_TOKEN ? { userId: GUEST } : null),
  };
  app.runtimeSpoolDatabase = { database: {}, ownerUserId: OWNER };
  app.config = { portalOrigin: "https://boss.example.com" };
  return app;
}

const GUEST_COOKIE = `cb_session=${GUEST_TOKEN}`;

test("从 /me 关掉开关，真的写进去了", () => {
  const store = storeFor();
  const app = bootApp({ store });

  assert.equal(store.readFor(GUEST).proactive.enabled, true, "默认是开的");

  const out = app.personalSiteSettings(GUEST_COOKIE, { proactive: { enabled: false } });

  assert.equal(out.ok, true);
  assert.equal(out.settings.proactive.enabled, false, "回给页面的必须是存进去的值");
  assert.equal(store.readFor(GUEST).proactive.enabled, false, "库里也要真的变了");
});

test("没有会话就改不了，请求体里也指定不了改谁", () => {
  const store = storeFor();
  const app = bootApp({ store });

  assert.equal(app.personalSiteSettings("", { proactive: { enabled: false } }).ok, false);
  assert.equal(app.personalSiteSettings("cb_session=nope", { proactive: { enabled: false } }).ok, false);
  // 身份只从 cookie 解：即使请求体里写了别人的 id，改的还是自己那一份。
  const out = app.personalSiteSettings(GUEST_COOKIE, { userId: OWNER, proactive: { enabled: false } });
  assert.equal(out.ok, true);
  assert.equal(store.read().proactive.enabled, true, "主人那一份不能被访客改到");
});

test("/me 的数据里带着当前设置，开关才显示得出状态", () => {
  const store = storeFor();
  const app = bootApp({ store });
  app.runtimeSpoolDatabase = {
    database: {},
    ownerUserId: OWNER,
    listUserItems: () => [],
  };
  app.listMemoriesFor = () => [];
  app.listOwnReminders = () => [];
  app.formatOwnerLocalTime = (v) => v;

  const site = app.buildPersonalSite(GUEST);

  assert.equal(site.ok, true);
  assert.equal(site.settings.proactive.enabled, true);
  assert.equal(typeof site.settings.proactive.quietStart, "number");
});

// ── 四、整条线接上了没有 ─────────────────────────────────────

test("portal server 接得住 personalSiteSettings，并且真的开了那条路由", () => {
  const server = new PortalHttpServer({
    portal: { handle: () => {} },
    personalSiteSettings: () => ({ ok: true }),
  });
  assert.equal(typeof server.personalSiteSettings, "function", "构造函数漏接＝整条路默默 404");

  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "portal", "portal-server.js"),
    "utf8",
  );
  assert.match(source, /pathname === "\/me\/api\/settings"/, "接了字段但没开路由还是 404");
});

test("app 真的把 personalSiteSettings 传给了 portal server", () => {
  const start = APP_SOURCE.indexOf("personalSiteData: (cookieHeader)");
  assert.notEqual(start, -1);
  const block = APP_SOURCE.slice(start, start + 400);
  assert.match(block, /personalSiteSettings:/);
});

// ── 五、后台看到的必须就是他那一页 ───────────────────────────

test("后台按人看到的字段，和这个人自己那一页完全一致", () => {
  const store = storeFor();
  const app = bootApp({ store });
  app.runtimeSpoolDatabase = {
    database: {},
    ownerUserId: OWNER,
    listUserItems: () => [],
  };
  app.listMemoriesFor = () => [];
  app.listOwnReminders = () => [];
  app.formatOwnerLocalTime = (v) => v;
  app.userAdmission = { users: { identify: () => ({ userId: GUEST }) } };
  app.channelAdapter = { resolveAccount: () => ({ accountId: "acct" }) };

  const mine = app.buildPersonalSite(GUEST);
  const boss = app.buildPersonDetail("wx-guest");

  // ok 只有 /me 那一侧有（它是个 HTTP 响应），其余每一样后台都得看得到。
  const mineKeys = Object.keys(mine).filter((k) => k !== "ok").sort();
  const bossKeys = Object.keys(boss).sort();
  assert.deepEqual(
    bossKeys,
    mineKeys,
    "两个出口是同一份数据。一边加了字段另一边没加，后台那一栏会显示出来但永远是空的",
  );
  assert.equal(boss.settings.proactive.enabled, true, "后台要看得到他的主动找我开着没");
});

test("后台按人看不到的那一半：认不出这个人时给的空壳字段也要齐", () => {
  const app = bootApp({ store: storeFor() });
  app.runtimeSpoolDatabase = { database: {}, ownerUserId: OWNER };
  const boss = app.buildPersonDetail("");
  // 空壳少一个键，前端读 detail.reminders 就是 undefined，那一栏直接不渲染。
  assert.deepEqual(
    Object.keys(boss).sort(),
    ["events", "media", "memories", "reminders", "settings", "todos"],
  );
});

test("轮询器排队的日志带上是给谁排的", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"),
    "utf8",
  );
  // 只有 id 的时候，「是不是只找主人」这个问题得解密数据库才答得出来。
  assert.match(source, /checkin queued id=\$\{queued\.id\} to=/);
});
