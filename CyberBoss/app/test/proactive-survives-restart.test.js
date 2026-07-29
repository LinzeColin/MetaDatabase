"use strict";

// 「我设置 1-4 小时，过了 4 小时它还没主动找我」。
//
// 原因不在间隔，在**倒计时只活在内存里**：进程一重启就重新掷一次骰子。
// 那天我部署了七八次，等于把倒计时按了七八次重置——它一次都轮不到。
// 这和部署频率无关：崩一次、重启一次、系统升级一次，效果一样。
//
// 参考仓里那个「随机轮询唤醒」是一个长跑进程，没人重启它，所以这个问题在那边
// 不存在。这里每次部署都要重启，就必须把「下一次什么时候」写到盘上。
//
// 第二件事：它差点发错人。目标是靠「最近一条属于主人的来信」找的，而当时收信
// 层没传 user_id，数据库把每个人的消息都记成主人的——于是最近那条其实是访客
// 发的，主动打招呼的目标就变成了刚扫码进来的朋友。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createNextCheckinStore } = require("../src/app/system-checkin-poller");
const { CyberbossApp } = require("../src/core/app");

const OWNER_USER = `usr_${"o".repeat(24)}`;
const GUEST_USER = `usr_${"g".repeat(24)}`;
const OWNER_WECHAT = "wx-owner";
const GUEST_WECHAT = "wx-guest";

function storeIn(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-next-checkin-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return {
    directory,
    store: createNextCheckinStore(path.join(directory, "sub", "next-checkin.json")),
  };
}

// ── 倒计时要活过重启 ────────────────────────────────────────

test("下一次什么时候写到盘上，重启之后读回来还是同一个时刻", (t) => {
  const { store } = storeIn(t);
  const at = Date.parse("2026-07-29T10:00:00.000Z");

  store.write(at);

  assert.equal(store.read(), at, "重启之后读不回来，倒计时就等于每次重来");
});

test("没存过就返回 0——上层据此掷一次新的", (t) => {
  const { store } = storeIn(t);
  assert.equal(store.read(), 0);
});

test("用掉之后清掉，不会卡在同一个时刻上反复触发", (t) => {
  const { store } = storeIn(t);
  store.write(Date.now() + 60_000);
  store.clear();
  assert.equal(store.read(), 0);
});

test("文件坏了当没存过，不抛错——一个坏文件不该把轮询器搞崩", (t) => {
  const { directory, store } = storeIn(t);
  const file = path.join(directory, "sub", "next-checkin.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, "这不是 JSON", "utf8");

  assert.equal(store.read(), 0);
});

test("负数和非数字一律当没存过", (t) => {
  const { directory, store } = storeIn(t);
  const file = path.join(directory, "sub", "next-checkin.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  for (const bad of ['{"nextAtMs":-1}', '{"nextAtMs":"明天"}', "{}"]) {
    fs.writeFileSync(file, bad, "utf8");
    assert.equal(store.read(), 0, `${bad} 应该当成没存过`);
  }
});

test("目录不存在也能写进去", (t) => {
  const { store } = storeIn(t);
  const at = Date.now() + 3_600_000;
  store.write(at);
  assert.equal(store.read(), at);
});

test("轮询器真的用了这个存储，而不是每轮现掷", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/app/system-checkin-poller.js"), "utf8",
  );
  assert.match(source, /nextCheckinStore\.read\(\)/);
  assert.match(source, /nextCheckinStore\.write\(nextAtMs\)/);
  assert.match(source, /nextCheckinStore\.clear\(\)/);
  // 存的时刻比现在设置的最大间隔还远，说明主人把间隔调短了，要重掷。
  assert.match(source, /nextAtMs > Date\.now\(\) \+ currentRange\.maxIntervalMs/);
});

test("到点时机器是关着的，开机后补发而不是跳过", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/app/system-checkin-poller.js"), "utf8",
  );
  // 关键是这条分支存在：waitMs <= 0 时不 continue，而是缓一下继续往下走。
  assert.match(source, /停机期间到点了/);
  assert.ok(
    !/waitMs <= 0[\s\S]{0,200}continue;/.test(source),
    "过期就 continue 等于永远补不上",
  );
});

// ── 目标必须是主人 ──────────────────────────────────────────

test("主动打招呼的目标从发件人本身推，不看那一行存着的 user_id", () => {
  const app = Object.create(CyberbossApp.prototype);
  app.runtimeSpoolDatabase = {
    ownerUserId: OWNER_USER,
    // 这是真实发生过的数据：访客的消息带着**主人的** user_id，因为收信层
    // 当时没传，数据库默认记成主人。
    listRecentInboundForOwner: () => [
      { userId: OWNER_USER, payload: { senderId: GUEST_WECHAT, accountId: "guest-bot" } },
      { userId: OWNER_USER, payload: { senderId: OWNER_WECHAT, accountId: "owner-bot" } },
    ],
    listUserRolesForOwner: () => new Map([[OWNER_USER, "owner"]]),
  };
  // 从发件人推出来的才是真的。
  app.userAdmission = {
    users: {
      identify: ({ senderRef }) => ({
        userId: senderRef === OWNER_WECHAT ? OWNER_USER : GUEST_USER,
      }),
    },
  };

  assert.equal(
    app.resolveOwnerSenderIdForCheckin(),
    OWNER_WECHAT,
    "主动打招呼发给了刚扫码进来的朋友，而主人自己一条都收不到",
  );
});

test("推不出来就返回空串——宁可不发，也不能发错人", () => {
  const app = Object.create(CyberbossApp.prototype);
  app.runtimeSpoolDatabase = {
    ownerUserId: OWNER_USER,
    listRecentInboundForOwner: () => [
      { userId: OWNER_USER, payload: { senderId: GUEST_WECHAT, accountId: "guest-bot" } },
    ],
    listUserRolesForOwner: () => new Map(),
  };
  app.userAdmission = { users: { identify: () => ({ userId: GUEST_USER }) } };

  assert.equal(app.resolveOwnerSenderIdForCheckin(), "");
});

test("库读不出来时返回空串，不抛错", () => {
  const app = Object.create(CyberbossApp.prototype);
  app.runtimeSpoolDatabase = null;
  assert.equal(app.resolveOwnerSenderIdForCheckin(), "");
});
