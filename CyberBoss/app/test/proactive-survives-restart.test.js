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

// ── 倒计时要活过重启，而且每人一份 ────────────────────────
//
// 一开始这里只有一个数字：主人那一个倒计时。现在是一张时刻表——「每个用户的
// 设置应该都是个人的」，五个人五个不同的间隔，用一个数字排不出来。

const OWNER_SENDER = "wx-owner";
const GUEST_SENDER = "wx-guest";

test("每个人的下一次分开存，重启之后读回来还是各自那个时刻", (t) => {
  const { store } = storeIn(t);
  const ownerAt = Date.parse("2026-07-29T10:00:00.000Z");
  const guestAt = Date.parse("2026-07-29T14:30:00.000Z");

  store.write(OWNER_SENDER, ownerAt);
  store.write(GUEST_SENDER, guestAt);

  assert.equal(store.read(OWNER_SENDER), ownerAt, "重启之后读不回来，倒计时就等于每次重来");
  assert.equal(store.read(GUEST_SENDER), guestAt);
});

test("给一个人重排，不动别人的", (t) => {
  const { store } = storeIn(t);
  store.write(OWNER_SENDER, 1_000_000);
  store.write(GUEST_SENDER, 2_000_000);

  store.write(OWNER_SENDER, 3_000_000);

  assert.equal(store.read(GUEST_SENDER), 2_000_000, "改一个人的间隔把别人的也重掷了");
});

test("升级不清零：老格式（只有主人那一个数字）还读得出来", (t) => {
  const { directory, store } = storeIn(t);
  const file = path.join(directory, "sub", "next-checkin.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // 这是升级前盘上真实的样子。
  fs.writeFileSync(file, JSON.stringify({ nextAtMs: 1_234_567 }), "utf8");

  assert.equal(
    store.readAll().__owner__,
    1_234_567,
    "升级那一刻所有人的倒计时被清零，等于又按了一次重置",
  );
});

test("没存过就返回 0——上层据此掷一次新的", (t) => {
  const { store } = storeIn(t);
  assert.equal(store.read(OWNER_SENDER), 0);
  assert.deepEqual(store.readAll(), {});
});

test("忘掉一个人不影响其他人", (t) => {
  const { store } = storeIn(t);
  store.write(OWNER_SENDER, 1_000_000);
  store.write(GUEST_SENDER, 2_000_000);

  store.forget(GUEST_SENDER);

  assert.equal(store.read(GUEST_SENDER), 0);
  assert.equal(store.read(OWNER_SENDER), 1_000_000);
});

test("文件坏了当没存过，不抛错——一个坏文件不该把轮询器搞崩", (t) => {
  const { directory, store } = storeIn(t);
  const file = path.join(directory, "sub", "next-checkin.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, "这不是 JSON", "utf8");

  assert.deepEqual(store.readAll(), {});
});

test("负数和非数字一律当没存过", (t) => {
  const { directory, store } = storeIn(t);
  const file = path.join(directory, "sub", "next-checkin.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  for (const bad of ['{"targets":{"wx-owner":-1}}', '{"targets":{"wx-owner":"明天"}}', "{}"]) {
    fs.writeFileSync(file, bad, "utf8");
    assert.equal(store.read(OWNER_SENDER), 0, `${bad} 应该当成没存过`);
  }
});

test("目录不存在也能写进去", (t) => {
  const { store } = storeIn(t);
  const at = Date.now() + 3_600_000;
  store.write(OWNER_SENDER, at);
  assert.equal(store.read(OWNER_SENDER), at);
});

test("轮询器真的用了这张时刻表，而不是每轮现掷", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/app/system-checkin-poller.js"), "utf8",
  );
  assert.match(source, /nextCheckinStore\.readAll\(\)/);
  assert.match(source, /nextCheckinStore\.write\(target\.senderId/);
  // 存的时刻比现在设置的最大间隔还远，说明间隔被调短了，要重掷。
  assert.match(source, /dueAt > now \+ range\.maxIntervalMs/);
});

test("到点了先把下一次排上，再决定这一次发不发", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/app/system-checkin-poller.js"), "utf8",
  );
  // 顺序反了的话，静默时段那条 continue 会让它卡在同一个时刻上反复触发。
  const body = source.slice(source.indexOf("if (dueAt > now)"));
  assert.ok(
    body.indexOf("nextCheckinStore.write(") < body.indexOf("enabled !== true"),
    "排下一次排在了判断之后",
  );
});

test("每人一份设置：谁开着就发谁的，不看别人", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/app/system-checkin-poller.js"), "utf8",
  );
  assert.match(source, /const targets = listTargets\(\)/);
  assert.match(source, /rangeFrom\(target\.settings\)/);
  assert.match(source, /isQuietNow\(target\.settings/);
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

// ── 中途改设置要当场算数 ────────────────────────────────────

test("三十秒扫一遍，中途改设置能被看见", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/app/system-checkin-poller.js"), "utf8",
  );
  // 一觉睡到点的话，把间隔从 4 小时改成 5 分钟，轮询器还躺在两小时后的闹钟上，
  // 他等 5 分钟什么都等不到，只能以为又坏了。
  assert.match(source, /SLICE_MS = 30_000/);
  assert.match(source, /const targets = listTargets\(\)/);
});
