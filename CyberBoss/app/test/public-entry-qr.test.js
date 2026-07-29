"use strict";

// 公开页每人一张自己的码。
//
// iLink 的授权码扫一次就生成一个**属于扫码那个人**的 bot 号，而且一张码只对
// 一个人有效。所以「主人配一张静态码贴出去给所有人扫」这个做法本来就不成立
// ——之前 buildPublicEntry 就是那么干的：读 access.entryUrl 渲染一张图，
// 谁扫都是同一张。第二个人扫的时候那张码早就作废了。
//
// 改成现要之后，/join 变成一个**没有鉴权、但每次请求都会真的打一次 iLink**
// 的接口。所以下面的测试里，限流和票据白名单跟"能出码"一样重要：少了它们，
// 这一页就是一个放大器，随便谁都能拿它去刷别人的接口。
//
// 这个文件里的响应形状是照 iLink 真实返回写的（get_bot_qrcode 回
// qrcode + qrcode_img_content；get_qrcode_status 回 status，确认时带
// bot_token / ilink_bot_id / ilink_user_id）。别自己编——编出来的形状能让
// 整套测试全绿而生产 100% 失效，这个仓已经栽过一次。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { listWeixinAccounts } = require("../src/adapters/channel/weixin/account-store");

const REAL_QR_LINK = "https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=fixture";
// 固定时刻。用真实量级的时间戳而不是 1000：限流是拿 now - lastMintedAt 比的，
// 1970 年那几秒会让第一次出码就被自己的限流拦掉。
const T0 = Date.parse("2026-07-29T05:00:00.000Z");

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-join-qr-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return `http://127.0.0.1:${server.address().port}/`;
}

// 一个假的 iLink。只实现出码和查状态两条，形状照真的写。
async function fakeIlink(t, { status = () => ({ status: "wait" }) } = {}) {
  const calls = { qrcode: 0, status: 0 };
  let serial = 0;
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    response.setHeader("content-type", "application/json");
    if (url.pathname.endsWith("/get_bot_qrcode")) {
      calls.qrcode += 1;
      serial += 1;
      response.writeHead(200);
      response.end(JSON.stringify({
        qrcode: `qr-ticket-${serial}`,
        qrcode_img_content: `${REAL_QR_LINK}-${serial}`,
      }));
      return;
    }
    if (url.pathname.endsWith("/get_qrcode_status")) {
      calls.status += 1;
      response.writeHead(200);
      response.end(JSON.stringify(status(url.searchParams.get("qrcode") || "")));
      return;
    }
    response.writeHead(404);
    response.end("{}");
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);
  return { baseUrl, calls };
}

function borrowApp(t, baseUrl, { bound = true, used = 0, seats = 5 } = {}) {
  const directory = temporaryDirectory(t);
  const stateDir = path.join(directory, "state");
  const app = Object.create(CyberbossApp.prototype);
  app.config = {
    stateDir,
    accountsDir: path.join(stateDir, "accounts"),
    syncBufferDir: path.join(stateDir, "sync-buffers"),
    weixinBaseUrl: baseUrl,
    weixinQrBotType: 3,
    ownerSenderIds: [],
  };
  app.publicEntryGate = { lastMintedAt: 0, tickets: new Map() };
  app.userAdmission = {
    ownerChannelBound: () => bound,
    users: { countActiveOrdinaryUsers: () => used },
  };
  app.personaStore = { read: () => ({ access: { mode: "open", seats, entryUrl: "" } }) };
  app.noteForDashboard = () => {};
  return app;
}

// ── 主人没绑好之前一张码都不出 ─────────────────────────────

test("主人自己都还没绑上的时候不出码——那时候放人进来只会绑出一堆没人管的号", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl, { bound: false });

  const entry = await app.buildPublicEntry();

  assert.equal(entry.ready, false);
  assert.equal(entry.status, "pending_activation");
  assert.equal(ilink.calls.qrcode, 0, "没绑好还去打了 iLink");
});

// ── 每个人拿到的是不同的、现要的码 ─────────────────────────

test("每来一个人现要一张新的码——iLink 的授权码本来就是一次性的", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl);

  const first = await app.mintPublicEntryQr({ now: T0 });
  const second = await app.mintPublicEntryQr({ now: T0 + 10_000 });

  assert.equal(first.ready, true);
  assert.equal(second.ready, true);
  assert.notEqual(first.ticket, second.ticket, "两个人拿到了同一张码");
  assert.equal(ilink.calls.qrcode, 2);
  assert.match(first.qrDataUri, /^data:image\/svg\+xml/);
});

test("回给公开页的东西里没有 token、没有 accountId、没有任何人的身份", async (t) => {
  const ilink = await fakeIlink(t, {
    status: () => ({
      status: "confirmed",
      bot_token: "secret-bot-token",
      ilink_bot_id: "5552be32014a@im.bot",
      ilink_user_id: "o9cq80yp-y0grRXWhi9UmK80uHAo@im.wechat",
      baseurl: "https://ilinkai.weixin.qq.com",
    }),
  });
  const app = borrowApp(t, ilink.baseUrl);

  const minted = await app.mintPublicEntryQr({ now: T0 });
  const status = await app.pollPublicEntryQr(minted.ticket, { now: T0 + 2_000 });

  assert.equal(status.state, "confirmed");
  const serialized = JSON.stringify(status);
  assert.ok(!serialized.includes("secret-bot-token"), "把 bot_token 吐给公开页了");
  assert.ok(!serialized.includes("5552be32014a"), "把 accountId 吐给公开页了");
  assert.ok(!serialized.includes("im.wechat"), "把扫码人的微信身份吐给公开页了");
  assert.deepEqual(Object.keys(status).sort(), ["message", "ok", "state"]);
});

test("扫码确认之后，那个人的号真的落到盘上了——不落盘就等于什么都没发生", async (t) => {
  const ilink = await fakeIlink(t, {
    status: () => ({
      status: "confirmed",
      bot_token: "guest-bot-token",
      ilink_bot_id: "guest-bot-id",
      ilink_user_id: "guest-wechat",
      baseurl: "https://ilinkai.weixin.qq.com",
    }),
  });
  const app = borrowApp(t, ilink.baseUrl);

  const minted = await app.mintPublicEntryQr({ now: T0 });
  await app.pollPublicEntryQr(minted.ticket, { now: T0 + 2_000 });

  const saved = listWeixinAccounts(app.config);
  assert.deepEqual(saved.map((account) => account.accountId), ["guest-bot-id"]);
  assert.equal(saved[0].userId, "guest-wechat");
  assert.equal(saved[0].token, "guest-bot-token");
});

test("确认过的票立刻作废，不会被拿去反复查", async (t) => {
  const ilink = await fakeIlink(t, {
    status: () => ({
      status: "confirmed", bot_token: "t", ilink_bot_id: "b", ilink_user_id: "u",
    }),
  });
  const app = borrowApp(t, ilink.baseUrl);
  const minted = await app.mintPublicEntryQr({ now: T0 });

  await app.pollPublicEntryQr(minted.ticket, { now: T0 + 2_000 });
  const callsAfterConfirm = ilink.calls.status;
  const again = await app.pollPublicEntryQr(minted.ticket, { now: T0 + 3_000 });

  assert.equal(again.state, "expired");
  assert.equal(ilink.calls.status, callsAfterConfirm, "作废的票还被拿去打了 iLink");
});

// ── 限流：这一页没有鉴权，所以次数必须被自己封死 ──────────

test("两次出码之间隔太近就不出——这一页没有鉴权，每次出码都会真的打一次 iLink", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl);

  const first = await app.mintPublicEntryQr({ now: T0 });
  const tooSoon = await app.mintPublicEntryQr({ now: T0 + 100 });

  assert.equal(first.ready, true);
  assert.equal(tooSoon.ready, false);
  assert.equal(tooSoon.status, "busy");
  assert.equal(ilink.calls.qrcode, 1, "限流没拦住，还是打了第二次");
});

test("在手的码太多就不再出——否则一个人刷新一百次就能拿走一百张", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl);

  let now = T0;
  let lastReady = null;
  for (let index = 0; index < 25; index += 1) {
    now += 5_000;
    lastReady = await app.mintPublicEntryQr({ now });
  }

  assert.equal(lastReady.ready, false);
  assert.equal(lastReady.status, "busy");
  assert.ok(ilink.calls.qrcode <= 20, `出了 ${ilink.calls.qrcode} 张，上限该是 20`);
});

test("只认自己发出去的票——不然任何人都能拿编造的票号驱使我去打 iLink", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl);

  const forged = await app.pollPublicEntryQr("我自己编的票号", { now: T0 });

  assert.equal(forged.state, "expired");
  assert.equal(ilink.calls.status, 0, "拿编造的票号打了 iLink");
});

test("过期的票会被丢掉，票池不会无限涨", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl);

  const minted = await app.mintPublicEntryQr({ now: T0 });
  assert.equal(app.publicEntryGate.tickets.size, 1);

  // 六分钟之后：iLink 的授权码早过期了。
  const stale = await app.pollPublicEntryQr(minted.ticket, { now: T0 + 7 * 60_000 });

  assert.equal(stale.state, "expired");
  assert.equal(app.publicEntryGate.tickets.size, 0);
  assert.equal(ilink.calls.status, 0, "过期的票还被拿去打了 iLink");
});

test("iLink 出错的时候公开页只看到一句中文，不看到任何内部错误码", async (t) => {
  const server = http.createServer((request, response) => {
    response.writeHead(500, { "content-type": "text/plain" });
    response.end("Bearer leaked-token-should-never-surface");
  });
  t.after(() => server.close());
  const baseUrl = await listen(server);
  const app = borrowApp(t, baseUrl);

  const entry = await app.mintPublicEntryQr({ now: T0 });

  assert.equal(entry.ready, false);
  assert.ok(!JSON.stringify(entry).includes("leaked-token"));
  assert.match(entry.message, /过一会儿再试/);
});

// ── 名额满了不是拒绝 ────────────────────────────────────────

test("名额满了照样出码，只是告诉他要自己填密钥——不是把人挡在门外", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl, { used: 5, seats: 5 });

  const entry = await app.mintPublicEntryQr({ now: T0 });

  assert.equal(entry.ready, true, "名额满了就不给码，那是把人挡在门外");
  assert.match(entry.message, /密钥/);
});

test("席位数读不出来的时候按还有名额说话——把能用的人挡住比多说一句糟糕得多", async (t) => {
  const ilink = await fakeIlink(t);
  const app = borrowApp(t, ilink.baseUrl);
  app.personaStore = { read: () => { throw new Error("库坏了"); } };

  assert.match(app.publicEntryQuotaNotice(), /扫这个码/);
});

// ── 页面本身 ────────────────────────────────────────────────

test("公开页会查扫码进度，而且一个 innerHTML 都没有", () => {
  const source = fs.readFileSync(path.join(__dirname, "../templates/join.html"), "utf8");

  assert.match(source, /\/api\/join\/status\?t=/);
  assert.ok(!source.includes("innerHTML"), "公开页里出现了 innerHTML");
  // 公开页上一个运营数字都不该有。
  assert.ok(!/还剩\s*\d|已用|人数/.test(source));
});

test("portal 把两条公开接口都接上了——只接出码不接查进度，页面会一直转圈", () => {
  const source = fs.readFileSync(path.join(__dirname, "../src/core/app.js"), "utf8");
  assert.match(source, /publicEntry:\s*\(\)\s*=>\s*this\.buildPublicEntry\(\)/);
  assert.match(source, /publicEntryStatus:\s*\(ticket\)\s*=>\s*this\.pollPublicEntryQr\(ticket\)/);
});
