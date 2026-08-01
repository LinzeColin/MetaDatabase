"use strict";

// CB9-320 共享额度与压力下的中文排队/限流/确定性降级（AC-009 / AC-031）
//
//   AC-009 注入共享预算耗尽；确定性功能仍成功，模型请求排队或明确限流，
//          页面和微信**不出现密钥配置指令**。
//   AC-031 低内存/磁盘注入按固定顺序关闭：访客主动关心 → Owner 脉冲 →
//          媒体/浏览器 → 访客模型 → Owner 新任务排队；自愈模型调用 = 0。
//
// 顺序是按「关掉之后谁会发现」排的。反过来排（先停主人的活儿去保访客的问候）
// 在任何一个压力等级上都是错的，所以这条顺序必须是冻结的、逐格可测的。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  ALWAYS_ON,
  CAPABILITY_IDS,
  DEGRADATION_ORDER,
  LEVELS,
  allows,
  budgetExhaustedNotice,
  describe: describeLevel,
  disabledAt,
  throttleNotice,
} = require("../src/services/operations/degradation-ladder");
const { admits, evaluateResourceGate } = require("../src/services/operations/resource-gate");

// ── AC-031 冻结顺序 ───────────────────────────────────────

test("AC-031 关闭顺序和 AC 原文逐字一致", () => {
  assert.deepEqual([...CAPABILITY_IDS], [
    "guest_proactive",     // 访客主动关心
    "owner_pulse",         // Owner 脉冲
    "media_and_browser",   // 媒体/浏览器
    "guest_model",         // 访客模型
    "owner_new_tasks",     // Owner 新任务排队
  ]);
  assert.ok(Object.isFrozen(DEGRADATION_ORDER));
  for (const step of DEGRADATION_ORDER) {
    assert.ok(Object.isFrozen(step));
    assert.ok(step.label && step.effect, `${step.id} 没写清楚关掉之后会怎样`);
  }
});

test("AC-031 逐级加码——每升一级只多关，不会把关过的又打开", () => {
  // 单调性。少了这条，一个「high 比 elevated 关得少」的实现照样能让
  // 「critical 全关」这种端点断言通过。
  const levels = ["normal", "low", "elevated", "high", "severe", "critical"];
  let previous = [];
  for (const level of levels) {
    const off = disabledAt(level);
    for (const id of previous) {
      assert.ok(off.includes(id), `${level} 把 ${id} 又打开了`);
    }
    assert.ok(off.length >= previous.length, `${level} 关得比上一级还少`);
    previous = off;
  }
  assert.deepEqual([...disabledAt("critical")], [...CAPABILITY_IDS], "最高级没有全关");
  assert.deepEqual([...disabledAt("normal")], [], "正常状态就关了东西");
});

test("AC-031 访客的问候永远第一个被关，主人的活儿永远最后", () => {
  // 这是整条顺序的**理由**本身：先关没人会发现的，最后动主人的活儿。
  const firstOff = DEGRADATION_ORDER[0].id;
  const lastOff = DEGRADATION_ORDER[DEGRADATION_ORDER.length - 1].id;
  assert.equal(firstOff, "guest_proactive");
  assert.equal(lastOff, "owner_new_tasks");
  // 只关一级时，主人那边一点感觉都没有。
  const low = disabledAt("low");
  assert.deepEqual([...low], ["guest_proactive"]);
  for (const ownerThing of ["owner_pulse", "owner_new_tasks", "guest_model"]) {
    assert.ok(!low.includes(ownerThing), `刚有点压力就关了 ${ownerThing}`);
  }
});

test("AC-031 主人的新任务是**排队**不是拒绝", () => {
  const step = DEGRADATION_ORDER.find((s) => s.id === "owner_new_tasks");
  assert.match(step.effect, /排队/);
  assert.match(step.effect, /不丢/, "没说清楚任务会不会丢——那正是主人唯一关心的");
  assert.match(step.effect, /不打断/, "没说正在跑的那个会怎样");
});

// ── AC-009 确定性功能永远还在 ─────────────────────────────

test("AC-009 笔记、提醒、Timeline、查询在任何等级下都能用", () => {
  // FR-009 的原话是「**保持**」这些能力。它们不花模型钱也不吃内存——关掉既省
  // 不下什么，又让用户彻底没得用。
  for (const level of Object.keys(LEVELS)) {
    for (const capability of ALWAYS_ON) {
      assert.equal(allows(level, capability), true,
        `${level} 下把 ${capability} 关掉了——用户彻底没得用了`);
    }
  }
});

test("AC-009 就算访客模型关了，他的确定性功能一件不少", () => {
  assert.equal(allows("severe", "guest_model"), false, "severe 下访客模型应该已经排队了");
  for (const capability of ["notes", "reminders", "timeline", "queries", "diary", "location"]) {
    assert.equal(allows("severe", capability), true, `${capability} 跟着一起关了`);
  }
});

test("阶梯上没有的能力默认放行", () => {
  // 挡一个我们没想过的东西，比放行它更容易造成「某个功能莫名其妙不能用了，
  // 而且没人知道为什么」。
  assert.equal(allows("critical", "something_new_nobody_listed"), true);
  assert.equal(allows("normal", ""), true);
});

test("认不出来的等级按 normal 办，不按 critical", () => {
  // 反过来的话，一次读数失败会让整台机器进入最高降级——一个测量问题变成一次
  // 全面停服。
  for (const junk of ["", null, undefined, "PANIC", 3]) {
    assert.deepEqual([...disabledAt(junk)], [], `${String(junk)} 触发了降级`);
  }
});

// ── AC-009 中文文案里不许出现配置密钥的指令 ───────────────

test("AC-009 限流和额度耗尽的那两句话里没有任何配置指令", () => {
  // 这是这条 AC 唯一要挡的东西：一个新手在系统最忙的时候被要求去弄一个 API key。
  const FORBIDDEN = [/密钥/, /API[ _-]?Key/i, /\btoken\b/i, /配置/, /设置文件/,
    /服务器/, /\bprovider\b/i, /连接我的AI/, /连接自己的 AI/];
  for (const notice of [
    throttleNotice({ owner: false }),
    throttleNotice({ owner: true }),
    budgetExhaustedNotice(),
  ]) {
    for (const pattern of FORBIDDEN) {
      assert.ok(!pattern.test(notice), `限流文案里出现了 ${pattern}：${notice}`);
    }
    // 而且必须说清楚现在还能做什么，不是只说「不行」。
    assert.ok(/照常|照样/.test(notice), `没告诉用户还能做什么：${notice}`);
    // 中文。
    assert.ok(/[一-龥]/.test(notice));
  }
});

test("AC-009 主人和访客的限流话术不一样——但都不提密钥", () => {
  const owner = throttleNotice({ owner: true });
  const guest = throttleNotice({ owner: false });
  assert.notEqual(owner, guest, "对主人和对访客说同一句话");
  // 主人那句要说「排上了」，因为他的任务确实不会丢。
  assert.match(owner, /排上了/);
  assert.match(guest, /排上了|一会儿/);
});

test("AC-009 额度耗尽那句说明会自动恢复——不需要用户做任何事", () => {
  const notice = budgetExhaustedNotice();
  assert.match(notice, /明天/);
  assert.match(notice, /自动恢复/);
  assert.ok(!/请你|需要你|你去/.test(notice), `给用户派了活：${notice}`);
});

// ── AC-031 自愈路径零模型调用 ─────────────────────────────

test("AC-031 降级阶梯不 require 任何东西——从这里到模型没有路径", () => {
  // 「自愈模型调用=0」最硬的保证不是「我们没调」，是「这个模块根本够不着」。
  // resource-gate 用的就是这条规矩，这里照做。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "operations", "degradation-ladder.js"), "utf8");
  const requires = src.match(/require\(/g) || [];
  assert.equal(requires.length, 0,
    "降级阶梯 require 了别的模块——从降级判断到模型调用之间就有路径了");
});

test("AC-031 资源闸门同样够不着模型", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "operations", "resource-gate.js"), "utf8");
  assert.equal((src.match(/require\(/g) || []).length, 0);
});

// ── 和真实资源闸门对齐 ────────────────────────────────────

test("AC-031 低内存/低磁盘注入下，闸门拒绝且给出可修的原因", () => {
  // 阶梯负责「关什么」，闸门负责「现在是什么状态」。两边都真的跑一遍。
  const healthy = {
    freeMemoryBytes: 4 * 1024 * 1024 * 1024,
    freeDiskBytes: 40 * 1024 * 1024 * 1024,
    freeInodes: 500_000,
    queueDepth: 1,
    loadRatio: 0.2,
  };
  assert.equal(admits(evaluateResourceGate(healthy)), true);

  const lowMemory = evaluateResourceGate({ ...healthy, freeMemoryBytes: 64 * 1024 * 1024 });
  assert.equal(admits(lowMemory), false);
  assert.match(String(lowMemory.reasonCode), /MEMORY/);

  const lowDisk = evaluateResourceGate({ ...healthy, freeDiskBytes: 128 * 1024 * 1024 });
  assert.equal(admits(lowDisk), false);
  assert.match(String(lowDisk.reasonCode), /DISK/);
  // 闸门自己也必须报告它一次模型都没调（AC-031）。
  for (const verdict of [lowMemory, lowDisk]) {
    assert.equal(verdict.modelCalls, 0, "闸门在判断过程中调了模型");
  }
});

test("AC-031 读不到测量值时闸门拒绝——没测过的地板不是满足的地板", () => {
  // 这条是既有实现的性质，在这里再钉一次：降级决策建立在它之上。
  const partial = { freeMemoryBytes: 4e9, freeDiskBytes: 4e10, freeInodes: 5e5, queueDepth: 1 };
  assert.equal(admits(evaluateResourceGate(partial)), false, "缺一个测量值却放行了");
});

test("describe() 给运维一份能读的说明，且不泄漏给用户", () => {
  const report = describeLevel("high");
  assert.equal(report.level, "high");
  assert.deepEqual([...report.disabled], ["guest_proactive", "owner_pulse", "media_and_browser"]);
  assert.equal(report.steps.length, 3);
  assert.ok(report.always_on.includes("reminders"));
  assert.ok(Object.isFrozen(report));
  // 每一步都说清楚用户侧会怎样——运维看这个来判断「用户现在感觉得到吗」。
  for (const step of report.steps) {
    assert.ok(step.effect.length > 6, `${step.id} 的说明太短，等于没说`);
  }
});

test("LEVELS 覆盖阶梯的**每一格**，没有够不着的一级", () => {
  // 第一版只断言了最大值，于是 0/1/3/5 这种跳格的写法照样绿——而跳掉的 2 和 4
  // 意味着「只关到媒体/浏览器」和「只关到访客模型」两个状态永远到不了：阶梯上
  // 白写了两级，而且掉级时用户的体感是断崖而不是逐步变慢。
  const depths = new Set(Object.values(LEVELS));
  for (let depth = 0; depth <= CAPABILITY_IDS.length; depth += 1) {
    assert.ok(depths.has(depth), `深度 ${depth} 没有任何等级能到达`);
  }
  assert.equal(depths.size, CAPABILITY_IDS.length + 1, "有两个等级关的是同样多的东西");
});

// ── 接线：阶梯真的被真实路径读到了 ─────────────────────────

test("AC-031 轮询器在**排队之前**问阶梯，而且区分主人和访客", () => {
  // 这个仓的招牌坏法：模块写好了、单测全绿、没人调用。
  // 阶梯尤其容易变成死代码——它不报错，只是永远返回「什么都没关」。
  const poller = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8");
  assert.match(poller, /require\("\.\.\/services\/operations\/degradation-ladder"\)/,
    "轮询器没有接阶梯");
  assert.match(poller, /allows\(readPressure\(\), capability\)/);
  // 两级要分开判：一起判的话，要么主人平白少一级缓冲，要么第一级形同虚设。
  assert.match(poller, /target\.isOwner \? "owner_pulse" : "guest_proactive"/);

  // 判定必须排在 enqueue 之前——排进去的消息一定会被发出去。
  const gateAt = poller.indexOf("allows(readPressure()");
  const enqueueAt = poller.indexOf("queue.enqueue(");
  assert.ok(gateAt !== -1 && enqueueAt !== -1);
  assert.ok(gateAt < enqueueAt, "先排队再判压力——排进去的消息一定会发出去");
});

test("AC-031 listCheckinTargets 真的带出了 isOwner", () => {
  // 不带的话上面那个三元永远走 guest_proactive 分支：主人的脉冲和访客的问候
  // 同时被第一级关掉，阶梯上的第二级就白写了。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  assert.match(app, /targets\.push\(\{ senderId: id, settings, isOwner \}\)/);
  assert.match(app, /add\(this\.resolveOwnerSenderIdForCheckin\(\), ownerSettings, true\)/);
  assert.match(app, /readPressure: \(\) => this\.resourcePressureLevel\(\)/);
});

test("AC-031 压力等级是真测出来的，不是写死的常量", (t) => {
  const { CyberbossApp } = require("../src/core/app");
  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    config: { stateDir: process.cwd() },
  });
  const level = app.resourcePressureLevel({ now: 1 });
  assert.ok(Object.keys(LEVELS).includes(level), `给出了阶梯上没有的等级：${level}`);

  // 缓存生效：15 秒内不重复敲磁盘。在一台已经吃紧的机器上，为了判断「是不是
  // 吃紧」而每秒去 statfs 一次，本身就是在加压。
  const again = app.resourcePressureLevel({ now: 2 });
  assert.equal(again, level);
  assert.equal(app.resourcePressureCache.at, 1, "缓存被刷新了，等于没缓存");

  // 测不出来时退回 normal，不是 critical。
  const broken = Object.assign(Object.create(CyberbossApp.prototype), {
    config: { stateDir: "/这个路径不存在/也不该存在" },
  });
  assert.equal(broken.resourcePressureLevel({ now: 1 }), "normal",
    "一次读数失败把整台机器推进了最高降级");
});

test("AC-031 阶梯和闸门用的是同一份阈值", () => {
  // 两套阈值必然会漂，而漂开之后「闸门说不行」和「阶梯说正常」会同时成立。
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  assert.match(app, /DEFAULT_THRESHOLDS: RESOURCE_THRESHOLDS/);
  assert.ok(!/minFreeMemoryBytes:\s*\d/.test(app), "app.js 里另立了一套阈值");
});

test("AC-031 喂不同的读数必须给出不同的等级——不是一个写死的常量", (t) => {
  // 变异测试补出来的：把等级写死成 "critical"，上面那批断言全绿——因为
  // "critical" 也是一个合法等级。区分「测出来的」和「写死的」只有一个办法：
  // 喂两组不同的读数，看结果跟不跟着变。这和 CB9-250 的假时钟是同一件事。
  const { CyberbossApp } = require("../src/core/app");
  const app = Object.assign(Object.create(CyberbossApp.prototype), { config: {} });
  const level = (metrics, now) => {
    app.resourcePressureCache = null;
    return app.resourcePressureLevel({ now, measure: () => metrics });
  };

  const roomy = {
    freeMemoryBytes: 8 * 1024 ** 3, freeDiskBytes: 200 * 1024 ** 3,
    freeInodes: 5_000_000, loadRatio: 0.1,
  };
  assert.equal(level(roomy, 1), "normal", "机器很空却报了压力");

  // 只有内存紧 → 降一级。
  assert.equal(level({ ...roomy, freeMemoryBytes: 64 * 1024 ** 2 }, 2), "low");
  // 内存 + 磁盘同时见底 → 不止两级：那是最危险的组合，连日志都写不下去。
  const both = level({ ...roomy, freeMemoryBytes: 64 * 1024 ** 2, freeDiskBytes: 64 * 1024 ** 2 }, 3);
  assert.ok(["high", "severe", "critical"].includes(both), `双紧只降到了 ${both}`);
  // 全面见底 → 最高级。
  assert.equal(level({
    freeMemoryBytes: 1, freeDiskBytes: 1, freeInodes: 1, loadRatio: 99,
  }, 4), "critical");

  // 单调：越紧只会越低，不会反弹。
  const order = ["normal", "low", "elevated", "high", "severe", "critical"];
  assert.ok(order.indexOf(both) > order.indexOf("low"), "更紧的读数给出了更松的等级");
});
