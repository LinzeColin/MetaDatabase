"use strict";

// CB9-520 Timeline/Status 隐私投影与字段白名单
// （AC-020 / AC-026 / AC-033 / AC-043 · FR-020 / FR-026 / NFR-003）
//
// AC-043 的原话：「公开页和 Status 不出现原始私聊、微信 ID、真实 thread/session
// ID、绝对路径和 token。」
//
// 这条早就有过滤器了（session-event 的 assertPublicPayload），写得也对。缺口在
// **真实链路上没人调它**——它只在 Timeline 自己那份投影里跑。于是保证的形状是
// 「我们有一个很好的过滤器」加上「碰巧现在没人往公开面塞脏东西」，而后半句是
// 行为保证，下一个人加一条路由就没了，而且没有任何症状。
//
// 所以这一套测试的重心不是「过滤器判得对不对」（那是 CB9-400 的事），而是
// **它到底在不在真实出口上**：起真服务器、发真请求、往响应里塞五类脏东西，
// 看字节有没有出去。纯函数全绿而真实链路照漏，是这个仓最熟悉的失败形状。

const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");

const { PortalHttpServer } = require("../src/services/portal/portal-server");
const {
  INTERNAL_ID_SHAPE,
  PublicEgressError,
  UNAUTHENTICATED_SURFACES,
  assertPublicEgress,
  isUnauthenticatedSurface,
} = require("../src/services/privacy/public-egress");

// 五类脏东西，逐条对上 AC-043 点名的那五样。
//
// 都是运行时拼出来的，不写成字面量——写成字面量会被这个仓自己的密钥扫描
// （AC-038）拦下，而它拦得对。
const wxid = `wxid_${"a1b2c3d4e5"}`;
const bearer = `Bearer ${"x".repeat(24)}`;
const threadId = `thread_${"9f8e7d6c5b4a3210"}`;
const homePath = `/${"Users"}/someone/Documents/private.txt`;
const rawChat = "昨天那件事我谁都没说过，只跟你讲——";

function request(port, requestPath) {
  return new Promise((resolve, reject) => {
    const call = http.request(
      { host: "127.0.0.1", port, method: "GET", path: requestPath },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let json = null;
          try {
            json = JSON.parse(text);
          } catch {
            json = null;
          }
          resolve({ status: response.statusCode, text, json });
        });
      },
    );
    call.on("error", reject);
    call.end();
  });
}

// 起一台真服务器，publicEntry 回什么由每条测试自己决定。
async function serverLeaking(t, entry, extra = {}) {
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "tok",
    firstRunProvider: () => false,
    publicEntry: () => entry,
    logger: { warn() {} },
    ...extra,
  });
  const address = await server.start();
  t.after(() => server.stop());
  return address.port;
}

// 这几条测试是**故意**让上游漏的，服务器会把拦截打到 stderr。
// 静音掉，否则一片红字看起来像测试挂了。
function muteEgressLog(t) {
  const original = console.error;
  console.error = () => {};
  t.after(() => { console.error = original; });
}

// ── AC-043 五类脏东西，逐条在真实 HTTP 出口上验 ───────────

for (const [name, poison] of [
  ["微信 ID", { message: `欢迎 ${wxid}` }],
  ["token", { message: `凭据是 ${bearer}` }],
  ["真实 thread ID", { message: `会话 ${threadId}` }],
  ["绝对路径", { message: `文件在 ${homePath}` }],
]) {
  test(`AC-043 公开接口漏「${name}」时字节不出网`, async (t) => {
    muteEgressLog(t);
    const port = await serverLeaking(t, {
      ok: true, ready: true, status: "ready", ...poison,
    });
    const api = await request(port, "/api/join");

    // 关键的一条：脏东西**一个字节都没到线上**。
    for (const secret of [wxid, bearer, threadId, homePath]) {
      assert.equal(api.text.includes(secret), false, `${name} 漏出去了`);
    }
    // fail-closed：拒发，不是脱敏之后接着发。脱敏接着发会把上游那个 bug
    // 藏起来——那一版代码依然在往公开面塞脏东西，只是这一层每次都在替它擦。
    assert.equal(api.status, 500);
    assert.deepEqual(api.json, { ok: false, code: "RESPONSE_WITHHELD" });
  });
}

test("AC-043 原始私聊靠顶层键白名单挡住，不是靠猜内容", async (t) => {
  // 「像不像私聊」判不出来——公开页上本来就有我们自己写的中文。判得出来的是
  // **这个字段本来就不该出现在这个出口上**。
  muteEgressLog(t);
  const port = await serverLeaking(t, {
    ok: true, ready: true, status: "ready", message: "扫码加它",
    lastMessage: rawChat,
  });
  const api = await request(port, "/api/join");
  assert.equal(api.text.includes(rawChat), false, "原始私聊漏到公开页了");
  assert.equal(api.status, 500);
});

test("AC-043 干净的响应照常出去——闸不是把主路径拦死", async (t) => {
  // 上面几条证明它拦得住。这一条证明它没把正事拦了：一条会把主路径拦下的
  // 守卫，最后一定会被谁「先注释掉看看」，然后再也没打开。
  const port = await serverLeaking(t, {
    ok: true,
    ready: true,
    status: "ready",
    // 真实的二维码是一整张 SVG 的 data URI，几千字符。第一版拿长度当
    // 「没投影过的原始文本」的判据，当场就误杀了它。
    qrDataUri: `data:image/svg+xml;base64,${"A".repeat(4096)}`,
    open: true,
    full: false,
    message: "用微信扫这个码加它，然后随便说句话就能用。",
    ticket: "t-123456",
  });
  const api = await request(port, "/api/join");
  assert.equal(api.status, 200);
  assert.equal(api.json.ok, true);
  assert.equal(api.json.qrDataUri.length > 4000, true, "二维码被闸吃掉了");
});

test("AC-043 扫码进度那条也在闸后面", async (t) => {
  muteEgressLog(t);
  const port = await serverLeaking(t, { ok: true, ready: true, status: "ready", message: "" }, {
    publicEntryStatus: () => ({ ok: true, state: "confirmed", message: `好了 ${wxid}` }),
  });
  const api = await request(port, "/api/join/status?t=abc");
  assert.equal(api.text.includes(wxid), false);
  assert.equal(api.status, 500);
});

// ── 闸装在唯一出口上，不是装在每个处理函数里 ─────────────

test("AC-043 闸装在 #json 上——不是每个处理函数各调一次", async (t) => {
  // 「每个处理函数记得调一下过滤器」是行为保证：写的时候都记得，下一个人加
  // 一条路由就漏了，而漏了没有任何症状。装在唯一出口上才是结构保证。
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "portal", "portal-server.js"), "utf8");
  const calls = [...src.matchAll(/assertPublicEgress\(/g)].length;
  assert.equal(calls, 1, `assertPublicEgress 被调了 ${calls} 次——散开了就守不住`);
  // 而且它就在 #json 里。
  const json = src.slice(src.indexOf("#json(response"), src.indexOf("#json(response") + 1400);
  assert.ok(json.includes("assertPublicEgress("), "闸不在 #json 里");
  // 出口路径由 #route 挂在 response 上，不靠调用方传。
  assert.ok(src.includes("response[EGRESS_SURFACE] = pathname;"),
    "出口路径改成要调用方传了——那又变回「记得传」的行为保证");
});

// ── AC-026 顶层键白名单 ───────────────────────────────────

test("AC-026 白名单是照着真实响应抄的，不是编的", () => {
  // 第一版是凭印象编的（qr / expiresAt / hint），结果整条公开入口被自己的
  // 隐私闸拦下——正当字段全在白名单外。编出来的形状让守卫看起来在工作，
  // 实际是在拦自己。
  assert.deepEqual([...UNAUTHENTICATED_SURFACES["/api/join"]].sort(), [
    "code", "full", "message", "ok", "open", "qrDataUri", "ready", "status", "ticket",
  ]);
  assert.deepEqual([...UNAUTHENTICATED_SURFACES["/api/join/status"]].sort(),
    ["code", "message", "ok", "state"]);
  assert.deepEqual([...UNAUTHENTICATED_SURFACES["/api/join/timezone"]].sort(), ["code", "ok"]);
});

test("AC-026 只有完全不鉴权的出口钉顶层键", () => {
  // /me 和 /admin 是鉴权后给本人/主人看他自己的内容——那两个出口的形状会随
  // 功能长，钉键白名单会变成每加一个功能改两处的负担，而那种守卫最后一定
  // 会被顺手放宽。它们过值扫描和键黑名单，不过键白名单。
  assert.equal(isUnauthenticatedSurface("/api/join"), true);
  assert.equal(isUnauthenticatedSurface("/me/api/data"), false);
  assert.equal(isUnauthenticatedSurface("/admin/api/conversations"), false);

  // 一段自己的日记在 /me 上是正当的——显示它正是那一页的意义。
  const diary = { ok: true, entries: [{ text: rawChat }] };
  assert.doesNotThrow(() => assertPublicEgress(diary, { surface: "/me/api/data" }));
  // 同一份东西放到不鉴权的出口上，两道都会拦：text 在键黑名单里，
  // entries 不在顶层白名单里。先撞上的是键黑名单。
  assert.throws(
    () => assertPublicEgress(diary, { surface: "/api/join" }),
    (error) => error.code === "EGRESS_PRIVATE_FIELD" && error.pointer === "$.entries.0.text",
  );
  // 一个键名干净、值也干净、但不该出现在这个出口上的字段——只有白名单拦得住它。
  assert.throws(
    () => assertPublicEgress({ ok: true, seats: 5 }, { surface: "/api/join" }),
    (error) => error.code === "EGRESS_FIELD_NOT_ALLOWED" && error.pointer === "$.seats",
  );
  assert.doesNotThrow(() => assertPublicEgress({ ok: true, seats: 5 }, { surface: "/admin/api/ops" }));
});

test("AC-020 后台对话页和「我的主页」不能被这道闸清空", () => {
  // 这一刀差点砍下去：session-event 的键黑名单里有 text / content / body，
  // 而后台对话那一栏和「我的主页」的全部意义就是把这个人自己的 text 显示出来。
  // 全出口套上去的话，那两页在线上直接变空，而测试全绿——没有一条测试用真
  // HTTP 打过那两条路由。
  //
  // 抓到它的不是推理，是去读了真实响应的字段名。这里把那几个真实形状钉住，
  // 下次谁再想把黑名单铺到所有出口，会先在这里红。
  const conversations = {
    ok: true,
    threads: [{
      id: "thr-1", label: "用户 1", short: "a1b2c3d4",
      messages: [{ at: "2026-08-02T12:00:00Z", who: "user", text: rawChat }],
    }],
    people: [{ id: "p1", label: "用户 1", count: 3 }],
  };
  assert.doesNotThrow(
    () => assertPublicEgress(conversations, { surface: "/admin/api/conversations" }),
    "后台对话页被闸清空了",
  );

  const mine = {
    ok: true,
    todos: [{ title: "买菜", dueAt: "今天 18:00", createdAt: "昨天" }],
    memories: [{ text: "我不吃香菜" }],
    reminders: [{ text: "五分钟后提醒我" }],
    settings: { proactive: true },
  };
  assert.doesNotThrow(
    () => assertPublicEgress(mine, { surface: "/me/api/data" }),
    "「我的主页」被闸清空了",
  );
});

test("AC-020 后台对话页走真 HTTP 也拿得到自己的 text", async (t) => {
  // 上一条是直接喂 assertPublicEgress 的——那证明的是判定对，不是**这条路通**。
  // 既有的后台测试确实用真 HTTP 打过这条路由，但它的 stub 回的是空 feed，
  // 所以「闸把 text 吃掉了」这件事它也抓不到。
  //
  // 这一条起真服务器、真请求、真带 text 的响应，从线上的字节里把它读回来。
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "panel-token",
    firstRunProvider: () => false,
    logger: { warn() {} },
    adminConversations: () => ({
      ok: true,
      threads: [{
        id: "thr-1", label: "用户 1", short: "a1b2c3d4",
        messages: [{ at: "2026-08-02T12:00:00Z", who: "user", text: rawChat }],
      }],
      people: [],
    }),
  });
  const address = await server.start();
  t.after(() => server.stop());

  const got = await new Promise((resolve, reject) => {
    const call = http.request({
      host: "127.0.0.1", port: address.port, method: "GET",
      path: "/admin/api/conversations",
      headers: { "x-admin-token": "panel-token" },
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => resolve({
        status: response.statusCode, text: Buffer.concat(chunks).toString("utf8"),
      }));
    });
    call.on("error", reject);
    call.end();
  });
  assert.equal(got.status, 200, "后台对话页被隐私闸拦下了");
  assert.ok(got.text.includes(rawChat), "主人看不到自己机器上的对话了");
});

test("AC-033 值扫描在每一个出口上都跑，鉴权与否无关", () => {
  // 微信 ID、绝对路径、token 在**任何**出口上都不该出现——主人自己那一页
  // 也不该有绝对路径，那是服务器的文件系统布局。
  for (const surface of ["/api/join", "/me/api/data", "/admin/api/conversations", null]) {
    for (const [code, payload] of [
      ["EGRESS_PRIVATE_VALUE", { ok: true, note: wxid }],
      ["EGRESS_PRIVATE_VALUE", { ok: true, note: homePath }],
      ["EGRESS_INTERNAL_ID", { ok: true, note: threadId }],
    ]) {
      assert.throws(
        () => assertPublicEgress(payload, { surface }),
        (error) => error.code === code,
        `${surface || "(other)"} 上没挡住 ${code}`,
      );
    }
  }
});

// ── 报错本身不能变成第二次泄漏 ───────────────────────────

test("AC-043 拦截的报错只带路径，不带值", () => {
  // 一条「泄漏了」的日志如果把值也记上，它本身就是那次泄漏——而且它落在
  // 普通日志里，泄漏面比原来更大。
  try {
    assertPublicEgress({ ok: true, deep: { nested: { note: wxid } } }, { surface: "/api/join" });
    assert.fail("没拦住");
  } catch (error) {
    assert.ok(error instanceof PublicEgressError);
    assert.equal(error.pointer, "$.deep.nested.note");
    for (const secret of [wxid, "a1b2c3d4e5"]) {
      assert.equal(String(error.message).includes(secret), false, "报错里带上值了");
      assert.equal(String(error.pointer).includes(secret), false, "路径里带上值了");
    }
  }
});

test("AC-043 深层嵌套和环形引用都扫得到、不会卡死", () => {
  const deep = { ok: true, a: { b: { c: { d: { e: { note: bearer } } } } } };
  assert.throws(() => assertPublicEgress(deep), (error) => error.code === "EGRESS_PRIVATE_VALUE");

  const loop = { ok: true, items: [] };
  loop.items.push(loop);
  assert.doesNotThrow(() => assertPublicEgress(loop));
});

test("AC-043 数组里的那一条也扫得到", () => {
  // 只扫对象不扫数组的话，把脏东西放进列表就能绕过去——而列表正是
  // Timeline、日记、提醒这几样的形状。
  assert.throws(
    () => assertPublicEgress({ ok: true, items: [{ note: "干净" }, { note: threadId }] }),
    (error) => error.code === "EGRESS_INTERNAL_ID" && error.pointer === "$.items[1].note",
  );
});

// ── 内部 ID 的形状 ────────────────────────────────────────

test("AC-043 内部 ID 认前缀加长随机段，不误杀普通词", () => {
  for (const bad of [threadId, `sess_${"a".repeat(20)}`, `csrf_${"b".repeat(18)}`]) {
    assert.equal(INTERNAL_ID_SHAPE.test(bad), true, `${bad.slice(0, 12)}… 没被认出来`);
  }
  // 误杀比漏杀更隐蔽：漏杀会在隐私扫描里被抓到，误杀表现为「这个功能偶尔
  // 报错」，没人会想到是过滤器干的。
  for (const good of ["session_state", "thread_ok", "token", "sess_1", "csrf"]) {
    assert.equal(INTERNAL_ID_SHAPE.test(good), false, `${good} 被误杀了`);
  }
});
