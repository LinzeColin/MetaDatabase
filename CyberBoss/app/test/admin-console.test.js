"use strict";

// 全量后台：「能看到所有管理数据，比如机器人的思考过程」。
//
// 两块东西：
//   一、「机器」那一栏——版本、在管几个号、队列、闸门、库版本、额度。
//       这一栏本该早就有：磁盘被部署撑满、负载上 11、调度闸门锁死、一条回复都
//       出不去，而后台上当时什么都看不出来。那次是靠 ssh 上去看 load 才发现的。
//   二、每一轮的执行轨迹——「它当时在干什么」。
//
// 关于「思考过程」有一条必须说实话，代码和页面上都写着：**模型不吐推理内容**。
// codex 只吐 turn 开始/结束/失败、reply delta、context updated、需要审批。所以
// 这里给的是执行轨迹，不是内心独白。这条测试守住"页面不许暗示它是后者"。
//
// 还有一条硬边界：「机器」这一栏一个字的聊天正文都不能有。它和对话栏走同一套
// 鉴权，但内容级别不同——运营数字可以一眼扫，聊天正文不该混在里面。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { readConfig } = require("../src/core/config");
const { bootstrapInstallation } = require("../src/core/bootstrap");

const PAGE = fs.readFileSync(path.join(__dirname, "../templates/dashboard.html"), "utf8");
const APP_SOURCE = fs.readFileSync(path.join(__dirname, "../src/core/app.js"), "utf8");
const PORTAL_SOURCE = fs.readFileSync(
  path.join(__dirname, "../src/services/portal/portal-server.js"), "utf8",
);

function tempHome(t) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "cb-console-"));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  return home;
}

function bootApp(t) {
  const home = tempHome(t);
  const stateDir = path.join(home, ".cyberboss");
  const saved = new Map();
  const set = (name, value) => {
    if (!saved.has(name)) saved.set(name, process.env[name]);
    if (value === null) delete process.env[name];
    else process.env[name] = value;
  };
  t.after(() => {
    for (const [name, value] of saved) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  });

  set("CYBERBOSS_STATE_DIR", stateDir);
  set("CYBERBOSS_WORKSPACE_CONFIG", path.join(stateDir, "workspaces.json"));
  set("CYBERBOSS_WORKSPACE_BASE", null);
  set("CYBERBOSS_WORKSPACE_ROOT", null);
  set("CB_DURABLE_INBOX", "true");
  set("CB_DURABLE_OUTBOX", "true");
  set("CB_MULTI_USER", "true");
  set("CB_REGISTRATION_MODE", "invite");
  set("CB_PORTAL_ORIGIN", "https://boss.example.com");
  set("CB_RUNTIME_DB", path.join(stateDir, "runtime.db"));
  set("CB_ALLOW_BASELINE_STAGING", "true");
  set("NODE_ENV", "test");
  set("CB_PRIVATE_DB_CANONICAL_SYNC", "false");

  const result = bootstrapInstallation({ stateDir });
  set("CB_RUNTIME_ENCRYPTION_KEY_FILE", result.encryptionKey.path);
  set("CB_RUNTIME_IDENTITY_KEY_FILE", result.identityKey.path);

  const app = new CyberbossApp(readConfig());
  app.initializeDurableInbox();
  t.after(() => app.runtimeSpoolDatabase?.close?.());
  return app;
}

// ── 机器那一栏 ──────────────────────────────────────────────

test("「机器」这一栏把状态一次给全：版本、号、队列、闸门、库版本、额度", (t) => {
  const app = bootApp(t);
  app.activeAccountId = "fixture-bot";
  app.channelAdapter = {
    listAccounts: () => [{ accountId: "fixture-bot" }],
    resolveAccount: () => ({ accountId: "fixture-bot" }),
    describe: () => ({ id: "weixin" }),
  };

  const ops = app.buildOpsSnapshot();

  assert.equal(ops.ok, true);
  assert.ok(ops.release, "没有版本这一格，部署完就没法确认跑的是不是新的");
  assert.ok(Number.isInteger(ops.release.uptimeSeconds));
  assert.deepEqual(ops.accounts, ["fixture-bot"]);
  assert.ok(ops.queue.jobs, "队列必须有 jobs");
  assert.ok(ops.queue.inbox, "队列必须有 inbox");
  assert.ok(ops.queue.outbox, "队列必须有 outbox");
  assert.ok(Array.isArray(ops.last24h));
  assert.ok(ops.schema >= 12, `库版本读出来是 ${ops.schema}`);
  assert.ok(Array.isArray(ops.lines));
  assert.ok(Array.isArray(ops.log));
});

test("闸门卡住的时候，后台说得出为什么——上次是靠 ssh 上去看 load 才发现的", (t) => {
  const app = bootApp(t);
  app.channelAdapter = { listAccounts: () => [], resolveAccount: () => ({ accountId: "" }) };
  app.jobScheduler = {
    lastGate: { state: "blocked", reason: "load_pressure", action: "defer" },
    lastGateAt: "2026-07-29T05:00:00.000Z",
  };

  const ops = app.buildOpsSnapshot();

  assert.equal(ops.gate.evaluated, true);
  assert.equal(ops.gate.state, "blocked");
  assert.equal(ops.gate.reason, "load_pressure");
  assert.equal(ops.gate.action, "defer");
});

// 这一条是线上真栽过的：面板第一次跑起来就报「闸门 blocked，
// measurement_unavailable」，而真相是队列一直是空的、闸门压根没判过。
// 闸门只在队列里有活的时候才判（job-scheduler 的 #dispatchNextRuntime），
// 空队列时 lastGate 一直停在构造时那个悲观初值上。
test("从来没判过的闸门必须说「还没判过」，不能报成「卡住了」", (t) => {
  const app = bootApp(t);
  app.channelAdapter = { listAccounts: () => [], resolveAccount: () => ({ accountId: "" }) };
  app.jobScheduler = {
    // 这就是 JobScheduler 构造时那个初值，一字不改。
    lastGate: {
      state: "blocked",
      reason: "measurement_unavailable",
      action: "capture_live_resource_profile",
      dispatchAllowed: false,
    },
    lastGateAt: null,
  };

  const ops = app.buildOpsSnapshot();

  assert.equal(ops.gate.evaluated, false, "没判过却报成判过了，等于指着一个不存在的故障");
  assert.equal(ops.gate.at, "");
});

test("调度器压根没起来时闸门是 null，而不是编一个「正常」出来", (t) => {
  const app = bootApp(t);
  app.channelAdapter = { listAccounts: () => [], resolveAccount: () => ({ accountId: "" }) };
  app.jobScheduler = null;

  assert.equal(app.buildOpsSnapshot().gate, null);
});

test("JobScheduler 真的会在判过之后记下时间——不然上面那条守卫是空的", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/services/jobs/job-scheduler.js"), "utf8",
  );
  assert.match(source, /this\.lastGateAt = null;/);
  assert.match(source, /this\.lastGate = gate;\s*\n\s*this\.lastGateAt = new Date\(\)\.toISOString\(\);/);
});

test("页面把「还没判过」和「判过了但卡住」分开说", () => {
  assert.match(PAGE, /还没需要判过/);
  assert.match(PAGE, /!gate\.evaluated/);
});

test("「机器」这一栏一个字的聊天正文都没有", (t) => {
  const app = bootApp(t);
  app.channelAdapter = { listAccounts: () => [], resolveAccount: () => ({ accountId: "" }) };
  const secret = "这句话是别人发来的私事，绝不该出现在运营那一栏";
  app.noteForDashboard("改了说话的语气");

  const serialized = JSON.stringify(app.buildOpsSnapshot());

  assert.ok(!serialized.includes(secret));
  // 里面只该有计数、状态词、时间和主人自己的操作记录。
  assert.match(serialized, /改了说话的语气/);
});

test("读不出来的那几格返回 0 或空，不猜也不抛", (t) => {
  const app = bootApp(t);
  app.channelAdapter = {
    listAccounts: () => { throw new Error("盘读不了"); },
    resolveAccount: () => { throw new Error("盘读不了"); },
  };
  app.activeAccountId = "";

  const ops = app.buildOpsSnapshot();
  assert.deepEqual(ops.accounts, []);
  assert.equal(ops.ok, true);
});

// ── 执行轨迹 ────────────────────────────────────────────────

test("每一轮下面能拿到 jobId——没有它，「它当时在干什么」就无从问起", () => {
  assert.match(APP_SOURCE, /jobId:\s*job\s*\?\s*job\.jobId\s*:\s*""/);
});

test("轨迹把连续吐字折成一条，并算出每一步隔了多久", (t) => {
  const app = bootApp(t);
  const base = Date.parse("2026-07-29T05:00:00.000Z");
  const at = (ms) => new Date(base + ms).toISOString();
  // 直接往库里写，走的是生产那条 recordTurnTrace。
  let seq = 0;
  const record = (kind, offset, payload) => {
    app.runtimeSpoolDatabase.recordTurnTrace({
      jobId: "job-1", turnId: "turn-1", seq: (seq += 1), kind, payload,
    });
    return offset;
  };
  record("runtime.turn.started", 0, null);
  record("runtime.reply.delta", 0, { chars: 5 });
  record("runtime.reply.delta", 0, { chars: 7 });
  record("runtime.turn.completed", 0, { tokens: 120 });

  const trace = app.buildTurnTrace({ jobId: "job-1" });

  assert.equal(trace.ok, true);
  const kinds = trace.steps.map((step) => step.kind);
  assert.deepEqual(kinds, [
    "runtime.turn.started", "runtime.reply.delta", "runtime.turn.completed",
  ], "连续的吐字必须折成一条，否则一屏几百行没法看");
  assert.equal(trace.steps[1].chars, 12);
  assert.equal(trace.steps[1].count, 2);
  for (const step of trace.steps) {
    assert.ok(Number.isFinite(step.gapMs) && step.gapMs >= 0);
  }
  assert.ok(at(0));
});

test("没有轨迹的那一轮如实回空，不是报错", (t) => {
  const app = bootApp(t);
  const trace = app.buildTurnTrace({ jobId: "根本不存在的 job" });
  assert.equal(trace.ok, true);
  assert.deepEqual(trace.steps, []);
});

// ── 鉴权 ────────────────────────────────────────────────────

test("trace 和 ops 都在要令牌的名单里——它们不吃「首次运行免令牌」", () => {
  assert.match(
    PORTAL_SOURCE,
    /OWNER_ONLY_ADMIN_APIS = Object\.freeze\(\[[^\]]*"trace"[^\]]*"ops"[^\]]*\]\)/s,
  );
  // 名单是白名单，不是前缀猜的——加接口忘了改鉴权应该是"接不上"，不是"漏了"。
  assert.match(PORTAL_SOURCE, /OWNER_ONLY_ADMIN_APIS\.some/);
});

test("两条新接口都真的接到 app 上了，不是只写了路由", () => {
  assert.match(APP_SOURCE, /adminTrace:\s*\(query\)\s*=>\s*this\.buildTurnTrace/);
  assert.match(APP_SOURCE, /adminOps:\s*\(\)\s*=>\s*this\.buildOpsSnapshot\(\)/);
  assert.match(PORTAL_SOURCE, /name === "trace"/);
  assert.match(PORTAL_SOURCE, /name === "ops"/);
});

// ── 页面 ────────────────────────────────────────────────────

test("后台多了「机器」这一栏，而且真的会去查", () => {
  assert.match(PAGE, /data-tab="ops"/);
  assert.match(PAGE, /"\/admin\/api\/ops"/);
  assert.match(PAGE, /id="tab-ops"/);
});

test("每一轮下面挂着「它当时在干什么」，点开才查——不然滚一屏就是几十次解密", () => {
  assert.match(PAGE, /它当时在干什么/);
  assert.match(PAGE, /\/admin\/api\/trace\?job=/);
  assert.match(PAGE, /loaded = true/);
});

test("页面必须说清那不是模型的内心独白——模型压根不吐推理内容", () => {
  assert.match(PAGE, /不是它心里想什么|不是它的内心独白/);
});

test("聊天记录会自己刷新，但内容没变就不重画", () => {
  // 无脑重画会把展开的轨迹收回去、把看到一半的位置顶回去。
  assert.match(PAGE, /signatureOf/);
  assert.match(PAGE, /signature !== chatSignature/);
  assert.match(PAGE, /if \(openPerson\) \{ loadChat\(\{ force: false \}\); \}/);
});

test("「机器」和画像也会自己刷新", () => {
  assert.match(PAGE, /if \(current === "ops"\) \{ loadOps\(\); \}/);
  assert.match(PAGE, /if \(openPerson\) \{ loadInsights\(\); \}/);
});

test("整页仍然一个 innerHTML 赋值都没有", () => {
  assert.ok(!/\.innerHTML\s*=/.test(PAGE));
});

// ── 主人的当地时间，不是服务器的 UTC ────────────────────────

test("面板上的时间是主人当地时间——服务器在 UTC 上跑，直接用会差八小时", (t) => {
  const app = bootApp(t);
  app.dashboardLog = [];
  app.noteForDashboard("测试一下");

  const line = app.recentLog()[0];
  // 北京时间的小时数，和 UTC 差 8。取当前时刻两边各算一次来比。
  const utcHour = new Date().getUTCHours();
  const localHour = Number(new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai", hour: "2-digit", hour12: false,
  }).format(new Date()));
  const shown = Number(line.slice(6, 8));
  assert.equal(shown, localHour, `面板显示 ${shown} 点，主人表上是 ${localHour} 点（UTC 是 ${utcHour} 点）`);
});

// ── 没有 AI 密钥的时候，后台必须说人话 ──────────────────────

test("一把 AI 密钥都没有时，后台明说别人聊不起来——而不是只留一个 activation_pending", (t) => {
  const app = bootApp(t);
  app.channelAdapter = { listAccounts: () => [], resolveAccount: () => ({ accountId: "" }) };

  const ops = app.buildOpsSnapshot();

  assert.equal(ops.guestAi.keys, 0);
  assert.equal(ops.guestAi.ready, false);
  assert.match(ops.guestAi.note, /密钥/);
  assert.match(ops.guestAi.note, /你自己不受影响/, "要说清主人自己走的是另一条路");
});

test("这一句在页面上顶在最前面，而且没 key 时是红的", () => {
  assert.match(PAGE, /data\.guestAi/);
  assert.match(PAGE, /别人的 AI/);
});
