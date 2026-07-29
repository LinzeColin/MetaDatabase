"use strict";

// 每个人自己那一页。
//
// 这一份守的是**隔离**：主人说「个人网站只有自己能看，但是我可以在 admin 看到
// 所有网站的信息」。前半句是对用户的承诺，必须真的成立——不是靠"没人会去猜别人
// 的 id"，而是靠这条路上**根本没有地方能填别人的 id**。
//
// 会话表 web_sessions 是所有人共用的（主人的后台会话也在里面），所以还要守住
// 反向那一条：普通人的会话不能变成后台的钥匙。

const assert = require("node:assert/strict");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");

const OWNER = `usr_${"o".repeat(24)}`;
const GUEST = `usr_${"g".repeat(24)}`;

// 令牌要长得像真的。parseSessionCookie 会拿 /^[A-Za-z0-9_-]{32,86}$/ 卡一道，
// 随手编个 "tok-guest" 根本进不了那扇门——测出来的绿是假的绿。
const GUEST_TOKEN = `g${"A1_-b2Cd".repeat(5)}xyz`;
const OWNER_TOKEN = `o${"Z9_-y8Xw".repeat(5)}abc`;

// 一个假的会话服务：token 映射到 user_id，够用来测边界。
function sessionsFor(map) {
  return {
    issue: ({ userId }) => ({ token: userId === OWNER ? OWNER_TOKEN : GUEST_TOKEN }),
    verify: ({ token }) => (map.has(token) ? { userId: map.get(token) } : null),
    cookieHeader: (token) => `cb_session=${token}; HttpOnly; SameSite=Strict`,
  };
}

function bootApp({ sessions, owner = OWNER } = {}) {
  const app = Object.create(CyberbossApp.prototype);
  app.adminSessionService = sessions;
  app.runtimeSpoolDatabase = { database: {}, ownerUserId: owner };
  app.config = { portalOrigin: "https://boss.example.com" };
  return app;
}

// ── 一、拿链接 ──────────────────────────────────────────────

test("发「主页」拿到的是自己那一页，票在 # 后面", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });

  const link = app.issuePersonalSiteLink(GUEST);

  assert.match(link, new RegExp(`^https://boss\\.example\\.com/me#t=${GUEST_TOKEN}`));
  assert.ok(
    !link.includes("?"),
    "票放进 query 就会进请求行，隧道和服务器的访问日志都会记下来",
  );
});

test("认不出这个人就不给链接，别发一条点开是空的", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });
  assert.equal(app.issuePersonalSiteLink(""), "");
  assert.equal(app.issuePersonalSiteLink("   "), "");
});

// ── 二、隔离：这条路上没有地方能填别人的 id ────────────────

test("这一页的身份只从 cookie 解，没有任何入参能指定看谁的", () => {
  const app = bootApp({
    sessions: sessionsFor(new Map([[GUEST_TOKEN, GUEST], [OWNER_TOKEN, OWNER]])),
  });
  const seen = [];
  app.buildPersonalSite = (userId) => {
    seen.push(userId);
    return { ok: true, todos: [], events: [], memories: [], reminders: [] };
  };

  app.personalSiteData(`cb_session=${GUEST_TOKEN}`);
  app.personalSiteData(`cb_session=${OWNER_TOKEN}`);

  assert.deepEqual(
    seen,
    [GUEST, OWNER],
    "谁的 cookie 就只能看到谁的——越权不该是一个要防的攻击，而该是一件写不出来的事",
  );
  // personalSiteData 只收一个 cookie 字符串，函数签名里就没有第二个参数。
  assert.equal(CyberbossApp.prototype.personalSiteData.length, 1);
});

test("没有 cookie、cookie 是编的、会话过期——一律拒绝，不是给一页空的", () => {
  const app = bootApp({ sessions: sessionsFor(new Map([[GUEST_TOKEN, GUEST]])) });
  app.buildPersonalSite = () => ({ ok: true, todos: [] });

  for (const header of ["", "cb_session=", "cb_session=编的", "别的cookie=x"]) {
    assert.equal(
      app.personalSiteData(header).ok,
      false,
      `「${header}」不该拿到任何数据`,
    );
  }
});

test("会话服务本身坏了也拒绝，不能失败开放", () => {
  const app = bootApp({
    sessions: {
      verify: () => { throw new Error("boom"); },
      cookieHeader: () => "",
    },
  });

  assert.equal(app.personalSiteData(`cb_session=${GUEST_TOKEN}`).ok, false);
  assert.equal(app.personalSiteLogin(GUEST_TOKEN).ok, false);
});

// ── 三、反向：普通人的会话不能变成后台的钥匙 ────────────────

test("普通人的会话进不了后台——两边共用一张 web_sessions 表", () => {
  const app = bootApp({
    sessions: sessionsFor(new Map([[GUEST_TOKEN, GUEST], [OWNER_TOKEN, OWNER]])),
  });

  assert.equal(
    app.adminSessionValid(`cb_session=${GUEST_TOKEN}`),
    false,
    "普通人发一句「主页」就拿到后台，等于所有人都能看所有人的数据",
  );
  assert.equal(app.adminSessionValid(`cb_session=${OWNER_TOKEN}`), true);
});

// ── 四、换票 ────────────────────────────────────────────────

test("票换成 cookie 之后，以后直接打开就行", () => {
  const app = bootApp({ sessions: sessionsFor(new Map([[GUEST_TOKEN, GUEST]])) });

  const result = app.personalSiteLogin(GUEST_TOKEN);

  assert.equal(result.ok, true);
  assert.match(result.cookie, /HttpOnly/);
  assert.match(result.cookie, /SameSite=Strict/);
});

test("编的票换不到 cookie", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });
  assert.equal(app.personalSiteLogin("随便编一个").ok, false);
  assert.equal(app.personalSiteLogin("").ok, false);
});

// ── 五、这一页装什么 ────────────────────────────────────────

test("只装这个人自己的四样：待办、日程、提醒、记着的事", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });
  const asked = [];
  app.runtimeSpoolDatabase = {
    database: {},
    ownerUserId: OWNER,
    listUserItems: ({ userId, kind }) => {
      asked.push({ userId, kind });
      return [{ id: "i1", title: "买菜", dueAt: null, createdAt: "2026-07-29T00:00:00.000Z" }];
    },
  };
  app.formatOwnerLocalTime = (value) => `本地(${value})`;
  app.listMemoriesFor = () => [{ category: "习惯", key: "sleep", text: "经常熬夜" }];
  app.listOwnReminders = () => [{ text: "到点了，喝水。", dueAt: "本地(x)" }];

  const page = app.buildPersonalSite(GUEST);

  assert.equal(page.ok, true);
  assert.deepEqual(
    asked.map((entry) => entry.userId),
    [GUEST, GUEST],
    "查的必须是这个人，不是主人也不是全部",
  );
  assert.deepEqual(asked.map((entry) => entry.kind), ["todo", "event"]);
  assert.equal(page.todos[0].title, "买菜");
  assert.equal(page.memories[0].text, "经常熬夜");
});

test("库还没起来就说没准备好，不是抛错让整页 500", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });
  app.runtimeSpoolDatabase = null;

  assert.equal(app.buildPersonalSite(GUEST).ok, false);
});

// ── 六、提醒是按人筛的，不能把别人的显示过来 ────────────────

test("提醒按发件人反推身份，认不出来就跳过", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });
  app.reminderQueue = {
    state: {
      reminders: [
        { senderId: "wx-guest", accountId: "bot-a", text: "到点了，喝水。", dueAtMs: 1 },
        { senderId: "wx-owner", accountId: "bot-b", text: "到点了，睡觉。", dueAtMs: 2 },
        { senderId: "wx-unknown", accountId: "bot-c", text: "别人的。", dueAtMs: 3 },
      ],
    },
  };
  app.userAdmission = {
    users: {
      identify: ({ senderRef }) => {
        if (senderRef === "wx-guest") { return { userId: GUEST }; }
        if (senderRef === "wx-owner") { return { userId: OWNER }; }
        throw new Error("认不出来");
      },
    },
  };
  app.formatOwnerLocalTime = () => "15:20";

  const mine = app.listOwnReminders(GUEST);

  assert.equal(mine.length, 1);
  assert.equal(mine[0].text, "到点了，喝水。");
});

test("认人服务不在就返回空——宁可少显示，也不能显示错", () => {
  const app = bootApp({ sessions: sessionsFor(new Map()) });
  app.userAdmission = null;
  app.reminderQueue = { state: { reminders: [{ senderId: "x", accountId: "y", text: "z", dueAtMs: 1 }] } };

  assert.deepEqual(app.listOwnReminders(GUEST), []);
});
