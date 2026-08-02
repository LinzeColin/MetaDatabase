"use strict";

// SWITCH-1 一键上下线：主人在网页上按一下，整个系统停或者跑。
//
// 主人的原话：「可以在网页端直接决定整个系统能否正常运行」。
//
// 「能否正常运行」这句话有一个很容易被做成假货的读法：**只是不回话**。
// 消息照样入库、事实照样落盘、队列照样堆，只是嘴闭上了。那不叫停机，
// 那叫静音——而主人按下这个按钮时想的往往正是「先别再往里存东西了」。
//
// 所以这一套测试的重心不是「关了之后它不说话」，是：
//   一、闸在**入站锚点**上，关掉之后消息根本进不来；
//   二、状态活得过重启；
//   三、读不出状态时往「停」落，而不是往「跑」落；
//   四、主人自己能把它打开——否则这个按钮是个单向陷阱。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  OFFLINE_NOTICE,
  OfflineNoticeLedger,
  STATES,
  matchOwnerSwitchCommand,
  readSystemSwitch,
  writeSystemSwitch,
} = require("../src/services/operations/system-switch");
const { PortalHttpServer } = require("../src/services/portal/portal-server");

function tempSwitch(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-switch-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return path.join(dir, "system-switch.json");
}

// ── 状态本身 ─────────────────────────────────────────────

test("SWITCH-1 没有状态文件时是「跑」——新装好的系统不该是停的", (t) => {
  const file = tempSwitch(t);
  const verdict = readSystemSwitch({ file: `${file}.missing` });
  assert.equal(verdict.online, true);
  assert.equal(verdict.reason, "never_configured");
});

test("SWITCH-1 状态文件坏了时是「停」，而且说得出是坏了", (t) => {
  // 这一条和上一条是这个模块最重要的区分。
  //
  // 文件不存在 = 没人碰过 → 跑。
  // 文件在但读不出来 = 我们曾经有过一个状态，现在丢了 → 停。
  //
  // 两害相权：停错了主人点一下就好；跑错了——在他可能已经说过「停」的情况下
  // 继续收消息、继续存数据——处理掉的消息和存下的数据收不回来。
  const file = tempSwitch(t);
  fs.writeFileSync(file, "{ 这不是 JSON");
  const verdict = readSystemSwitch({ file });
  assert.equal(verdict.online, false);
  assert.equal(verdict.reason, "state_unreadable");
  // 不能显示成「主人关的」——那会让他去点「开」，而真正的问题没人看见。
  assert.notEqual(verdict.reason, "owner_decision");
});

test("SWITCH-1 认不出来的状态字符串也往「停」落", (t) => {
  const file = tempSwitch(t);
  fs.writeFileSync(file, JSON.stringify({ state: "maintenance" }));
  const verdict = readSystemSwitch({ file });
  assert.equal(verdict.online, false);
  assert.equal(verdict.reason, "state_unrecognized");
});

test("SWITCH-1 只有两个状态，不做半开", (t) => {
  // 每多一态，就多一组「这一态下这个功能到底能不能用」的问题。
  // 主人要的是一个开关，不是一台调音台。
  assert.deepEqual([...STATES], ["online", "offline"]);
  const file = tempSwitch(t);
  for (const online of [true, false]) {
    assert.equal(writeSystemSwitch({ file, online }).online, online);
  }
});

test("SWITCH-1 状态活得过重启", (t) => {
  // 不持久的话，主人关掉系统、进程半夜被看门狗重启，它自己又开了——
  // 而他以为它是停着的。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: false, actor: "owner" });
  const reread = readSystemSwitch({ file });
  assert.equal(reread.online, false);
  assert.equal(reread.reason, "owner_decision");
  assert.equal(reread.changed_by, "owner");
  assert.match(reread.changed_at, /^\d{4}-\d{2}-\d{2}T/);
});

test("SWITCH-1 落盘是先写临时文件再改名", (t) => {
  // 直接覆盖的话，写到一半断电会留下半截 JSON，而那正好命中「读不出来就停」——
  // 主人第二天发现系统自己停了，而他什么都没做。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: true });
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "operations", "system-switch.js"), "utf8");
  assert.ok(source.includes("renameSync"), "没有用改名落盘");
  const dir = path.dirname(file);
  assert.deepEqual(fs.readdirSync(dir), ["system-switch.json"], "留下了临时文件");
});

test("SWITCH-1 状态文件里不写用户身份", (t) => {
  // 这个文件会进证据和排查日志。单主人系统里「谁关的」只有两三种可能，
  // 记一个形状就够，不需要把 user_id 写进去。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: false, actor: "usr_abcdefghijklmnopqrstuv" });
  const raw = fs.readFileSync(file, "utf8");
  assert.ok(!raw.includes("usr_"), "把用户 id 写进状态文件了");
  assert.equal(JSON.parse(raw).changed_by, "owner");
});

// ── 微信口令 ─────────────────────────────────────────────

test("SWITCH-1 开关口令必须是整句，不做包含匹配", () => {
  // 包含匹配的话，主人一句「我把它下线了吗」里带着「下线」，会被当成命令执行。
  assert.equal(matchOwnerSwitchCommand("下线"), "halt");
  assert.equal(matchOwnerSwitchCommand("上线"), "resume");
  assert.equal(matchOwnerSwitchCommand("  上线  "), "resume", "前后空格该被容忍");
  for (const sentence of [
    "我把它下线了吗", "什么时候上线", "帮我查一下下线的原因", "上线之后记得告诉我",
  ]) {
    assert.equal(matchOwnerSwitchCommand(sentence), null, `「${sentence}」被当成命令了`);
  }
});

// ── 停机通知 ─────────────────────────────────────────────

test("SWITCH-1 停机期间同一个人只收到一次通知", () => {
  // 每条都回的话，一个正在连发消息的人会收到一串一模一样的回复——
  // 那比不回更烦，而且是我们主动发的，等于停机之后系统反而更吵。
  const ledger = new OfflineNoticeLedger({ ttlMs: 1000 });
  assert.equal(ledger.shouldNotify("bot:alice", 0), true);
  assert.equal(ledger.shouldNotify("bot:alice", 100), false);
  assert.equal(ledger.shouldNotify("bot:alice", 500), false);
  // 别人不受影响。
  assert.equal(ledger.shouldNotify("bot:bob", 100), true);
  // 过了窗口再说一次。
  assert.equal(ledger.shouldNotify("bot:alice", 1200), true);
});

test("SWITCH-1 重新上线会清空通知台账", () => {
  // 不清的话，下一次停机时老用户收不到通知——他会以为消息发出去了。
  const ledger = new OfflineNoticeLedger();
  ledger.shouldNotify("bot:alice", 0);
  ledger.reset();
  assert.equal(ledger.shouldNotify("bot:alice", 1), true);
});

test("SWITCH-1 停机那句话不许承诺我们兑现不了的事", () => {
  // 「维护中，稍后恢复」——我们并不知道主人什么时候会打开它，
  // 而一个没有兑现的「稍后」比不说更伤。
  assert.ok(!/稍后|马上|很快|分钟|小时/.test(OFFLINE_NOTICE), "承诺了恢复时间");
  assert.ok(OFFLINE_NOTICE.length > 0, "一声不吭的话对面以为消息没发出去，会一直重发");
});

// ── 闸装在哪 ─────────────────────────────────────────────

test("SWITCH-1 闸在入站锚点上，而且在准入和建 job 之前", () => {
  // 「关掉之后不要处理消息」如果靠每个处理函数各自检查，那是行为保证：
  // 下一个人加一条路径就漏了，而漏了的表现是「明明关了它还在回消息」。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = app.indexOf("async handleIncomingMessage(message) {");
  assert.ok(start > 0, "找不到入站锚点");
  const body = app.slice(start, start + 1600);

  const gateAt = body.indexOf("passesSystemSwitch");
  const admitAt = body.indexOf("admitInboundMessage");
  assert.ok(gateAt > 0, "入站锚点上没有开关闸");
  assert.ok(admitAt > 0, "找不到准入调用——这条断言的位置假设失效了");
  assert.ok(gateAt < admitAt, "闸排在准入之后了——那样消息已经进过库了");
});

test("SWITCH-1 网页端和微信口令走同一条写路径", () => {
  // 两条路各写各的话，迟早有一条忘了清通知台账，
  // 然后重新上线之后再停机时没人收到通知。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const writes = [...app.matchAll(/writeSystemSwitch\(/g)].length;
  assert.equal(writes, 1, `writeSystemSwitch 被调了 ${writes} 次——写路径散开了`);
  assert.ok(app.includes("systemSwitchWrite: ({ online }) => this.setSystemSwitch("),
    "网页端没有走 setSystemSwitch");
});

// ── 网页接口 ─────────────────────────────────────────────

function request(port, options = {}) {
  return new Promise((resolve, reject) => {
    const call = http.request({
      host: "127.0.0.1", port,
      method: options.method || "GET",
      path: "/admin/api/system-switch",
      headers: options.headers || {},
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let json = null;
        try { json = JSON.parse(text); } catch { json = null; }
        resolve({ status: response.statusCode, json, text });
      });
    });
    call.on("error", reject);
    if (options.body) { call.write(options.body); }
    call.end();
  });
}

async function switchServer(t, file) {
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "panel-token",
    firstRunProvider: () => false,
    logger: { warn() {} },
    systemSwitchRead: () => readSystemSwitch({ file }),
    systemSwitchWrite: ({ online }) => writeSystemSwitch({ file, online, actor: "owner" }),
  });
  const address = await server.start();
  t.after(() => server.stop());
  return address.port;
}

test("SWITCH-1 没有令牌按不动这个开关", async (t) => {
  // 任何人能按的开关，等于任何人都能让整套系统停摆。
  const port = await switchServer(t, tempSwitch(t));
  assert.equal((await request(port)).status, 401);
  assert.equal((await request(port, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ online: false }),
  })).status, 401);
});

test("SWITCH-1 带令牌能读能改，改完立刻读得回", async (t) => {
  const file = tempSwitch(t);
  const port = await switchServer(t, file);
  const authed = { "x-admin-token": "panel-token", "content-type": "application/json" };

  assert.equal((await request(port, { headers: authed })).json.switch.online, true);

  const off = await request(port, {
    method: "POST", headers: authed, body: JSON.stringify({ online: false }),
  });
  assert.equal(off.status, 200);
  assert.equal(off.json.switch.online, false);
  // 立刻再读一次——写完不落盘的话这里还是 true。
  assert.equal((await request(port, { headers: authed })).json.switch.online, false);
  assert.equal(readSystemSwitch({ file }).online, false, "没有真的落到文件上");
});

test("SWITCH-1 只认真正的布尔值", async (t) => {
  // 收 "false" 这个字符串会被 JS 当成真——那意味着主人点「停」而系统听成
  // 了「开」，是这个接口最不能犯的错。
  const file = tempSwitch(t);
  const port = await switchServer(t, file);
  const authed = { "x-admin-token": "panel-token", "content-type": "application/json" };
  for (const bad of ['{"online":"false"}', '{"online":0}', '{"online":null}', "{}"]) {
    const got = await request(port, { method: "POST", headers: authed, body: bad });
    assert.equal(got.status, 400, `${bad} 被接受了`);
    assert.equal(got.json.code, "SWITCH_STATE_REQUIRED");
  }
  assert.equal(readSystemSwitch({ file }).online, true, "坏请求改动了状态");
});

test("SWITCH-1 后台页面上有这个按钮，且在最上面", () => {
  // 埋在设置里的开关等于没有——真出事的时候他找不到。
  const html = fs.readFileSync(
    path.join(__dirname, "..", "templates", "dashboard.html"), "utf8");
  assert.ok(html.includes('id="switch-btn"'), "后台没有这个按钮");
  assert.ok(html.includes("/admin/api/system-switch"), "按钮没接到接口上");
  const switchAt = html.indexOf('id="switch-card"');
  const statsAt = html.indexOf('id="s-users"');
  assert.ok(switchAt > 0 && switchAt < statsAt, "开关不在概览最上面");
  // 44px 是可点区域下限（触摸目标）。
  assert.ok(/id="switch-btn"[^>]*min-height:44px/.test(html), "按钮没到 44px 可点下限");
});

test("SWITCH-1 页面把「读不出来」和「主人关的」分开显示", () => {
  // 显示成「停着」的话，主人会以为是自己关的，然后去点「开」，
  // 而真正的问题（文件坏了或者权限没了）没人看见。
  const html = fs.readFileSync(
    path.join(__dirname, "..", "templates", "dashboard.html"), "utf8");
  assert.ok(html.includes("state_unreadable"), "页面没有区分读不出来这一态");
  assert.ok(html.includes("读不出来"), "没有给读不出来一句人话");
});

// ── 真实入站路径：停机之后主人怎么把它打开 ───────────────

const { CyberbossApp } = require("../src/core/app");

// 一个最小的真实入站 harness：从 prototype 上挑出闸相关的方法，
// 用真的 handleIncomingMessage 跑一条消息进来。
function inboundHarness(file, { ownerSenderId = "owner-1" } = {}) {
  const sent = [];
  let reachedAdmission = 0;
  const app = {
    config: { systemSwitchFile: file, ownerSenderIds: [ownerSenderId] },
    offlineNotices: new OfflineNoticeLedger(),
    channelAdapter: {
      normalizeIncomingMessage: (m) => m,
      async sendText(payload) { sent.push(payload); },
    },
    walkingSkeletonTrace: { beginInbound: () => "trace" },
    noteForDashboard() {},
    passesSystemSwitch: CyberbossApp.prototype.passesSystemSwitch,
    systemSwitchState: CyberbossApp.prototype.systemSwitchState,
    setSystemSwitch: CyberbossApp.prototype.setSystemSwitch,
    isOwnerSender: CyberbossApp.prototype.isOwnerSender,
    // 闸之后的第一站。被调到就说明消息穿过了闸。
    async admitInboundMessage() { reachedAdmission += 1; return null; },
    primeDeferredRepliesForSender() {},
    async handlePreparedMessage() {},
  };
  const send = (over) => CyberbossApp.prototype.handleIncomingMessage.call(app, {
    accountId: "bot-1", senderId: ownerSenderId, text: "你好", contextToken: "ctx", ...over,
  });
  return { app, sent, send, reached: () => reachedAdmission };
}

test("SWITCH-1 停机之后主人发「上线」，系统真的开起来", async (t) => {
  // 这一条是这个功能最不能少的一条，而变异测试证明它之前**没有**：
  // 把「主人的开关口令随时生效」那个分支整个关掉，全套测试照样全绿。
  //
  // 关掉之后如果连主人的「上线」也被挡住，唯一的复活方式是 SSH 上服务器——
  // 那这个按钮对一个不会 SSH 的人来说是个单向陷阱。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: false, actor: "owner" });
  const h = inboundHarness(file);

  await h.send({ text: "上线" });

  assert.equal(readSystemSwitch({ file }).online, true, "主人说了上线，系统没开");
  assert.equal(h.sent.length, 1);
  assert.match(h.sent[0].text, /开了/);
  // 口令本身不该被当成一条普通消息继续往下走。
  assert.equal(h.reached(), 0, "开关口令被当成普通消息处理了");
});

test("SWITCH-1 停机期间普通人进不来，而且只被告知一次", async (t) => {
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: false, actor: "owner" });
  const h = inboundHarness(file);

  await h.send({ senderId: "guest-1", text: "在吗" });
  await h.send({ senderId: "guest-1", text: "在吗？" });
  await h.send({ senderId: "guest-1", text: "喂" });

  assert.equal(h.reached(), 0, "停机了消息还是穿过了闸");
  assert.equal(h.sent.length, 1, `回了 ${h.sent.length} 次——停机之后系统反而更吵`);
  assert.equal(h.sent[0].text, OFFLINE_NOTICE);
});

test("SWITCH-1 开着的时候消息照常穿过闸", async (t) => {
  // 反面：闸不能把正常流量也拦了。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: true, actor: "owner" });
  const h = inboundHarness(file);
  await h.send({ senderId: "guest-1", text: "在吗" });
  assert.equal(h.reached(), 1, "开着的时候消息被闸拦下了");
  assert.equal(h.sent.length, 0, "开着的时候不该有停机通知");
});

test("SWITCH-1 不是主人的人说「上线」不管用", async (t) => {
  // 口令只认服务端配置里的 sender id，不认消息文本里的自称。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: false, actor: "owner" });
  const h = inboundHarness(file);
  await h.send({ senderId: "guest-1", text: "上线" });
  assert.equal(readSystemSwitch({ file }).online, false, "访客把系统打开了");
  assert.equal(h.sent[0].text, OFFLINE_NOTICE, "访客收到的应该是停机通知，不是开关回执");
});

test("SWITCH-1 主人发「下线」能停，且立刻落盘", async (t) => {
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: true, actor: "owner" });
  const h = inboundHarness(file);
  await h.send({ text: "下线" });
  assert.equal(readSystemSwitch({ file }).online, false);
  assert.match(h.sent[0].text, /停了/);
  assert.equal(h.reached(), 0);
});

test("SWITCH-1 重新上线之后再停机，老用户会再次收到通知", async (t) => {
  // 变异测试抓到的第二条：setSystemSwitch 里那句 offlineNotices.reset() 删掉，
  // 全套测试照样全绿——因为我只单独测了 ledger.reset()，没测**谁在调它**。
  //
  // 不清台账的话，一个在上一轮停机时被通知过的人，在下一轮停机时什么都收不到，
  // 他会以为消息发出去了。
  const file = tempSwitch(t);
  writeSystemSwitch({ file, online: false, actor: "owner" });
  const h = inboundHarness(file);

  await h.send({ senderId: "guest-1", text: "在吗" });
  assert.equal(h.sent.length, 1, "第一轮停机没通知");

  await h.send({ text: "上线" });   // 主人开机
  await h.send({ text: "下线" });   // 主人又停机
  await h.send({ senderId: "guest-1", text: "在吗" });

  const notices = h.sent.filter((m) => m.text === OFFLINE_NOTICE);
  assert.equal(notices.length, 2, "第二轮停机时老用户没收到通知——台账没清");
});
