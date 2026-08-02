"use strict";

// 主动打招呼。
//
// 参考仓（WenXiaoWendy/cyberboss）的「随机轮询唤醒」就是这件事：系统在随机时刻
// 戳醒模型，让它自己判断该说什么、还是什么都不说。这一整套代码本来就在这个仓里，
// 但生产上从来没通电——`CYBERBOSS_ENABLE_CHECKIN` 一次都没配过，日志里 checkin
// 出现 0 次。代码存在不等于产品有这个功能，这是本仓第六次栽在同一件事上。
//
// 两条边界必须钉死，因为踩过去就是真违规：
//   一、只对主人。R19 冻结的 zero_agent_runtime_cases 里 checkin 属于
//       must_remain_zero（那说的是给普通用户的确定性关心，纯模板零 token），
//       而唤醒模型这条只在 permitted_model_triggers 的 owner_codex_turn 之内。
//   二、静默时段。半夜三点戳人一下不叫陪伴。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  MAX_ALLOWED_MINUTES,
  MIN_ALLOWED_MINUTES,
  PROACTIVE_DEFAULTS,
  PersonaStore,
  defaultPersona,
  inQuietHours,
  normalizeProactive,
} = require("../src/services/persona/persona-store");
const { isQuietNow, rangeFrom } = require("../src/app/system-checkin-poller");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");

const ENCRYPTION_KEY = Buffer.alloc(32, 53);
const IDENTITY_KEY = Buffer.alloc(32, 59);

function openSpool(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-proactive-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  return spool;
}

// ── 默认必须是关的 ──────────────────────────────────────────

// 这条原来断言的是"默认不主动找人"。2026-07-30 主人明确改了：「它需要能主动去
// 找每个人，并且每个用户都能有单独的『主动找我』这个设置按钮」，并在被问到默认
// 值时选了「默认开，本人可以关」。默认关的话这个能力上线即死——没人会先去点一
// 个他不知道存在的开关。
test("默认主动找人，本人可以关", () => {
  assert.equal(defaultPersona().proactive.enabled, true);
  assert.equal(PROACTIVE_DEFAULTS.enabled, true);
  // 关得掉才叫开关：显式 false 不能被默认值盖回去。
  assert.equal(normalizeProactive({ enabled: false }).enabled, false);
});

test("默认频率比参考仓保守得多，而且默认有静默时段", () => {
  const { minMinutes, maxMinutes, quietStart, quietEnd } = defaultPersona().proactive;
  // 参考仓默认 3~60 分钟，平均每天四五十次模型调用。这里默认 45 分钟起。
  assert.ok(minMinutes >= 30, `默认最短间隔 ${minMinutes} 分钟太密了`);
  assert.ok(maxMinutes >= minMinutes);
  assert.notEqual(quietStart, quietEnd, "默认必须有一段不打扰的时间");
});

// ── 设置归一化 ──────────────────────────────────────────────

test("间隔被夹在允许范围内，且上限永远不低于下限", () => {
  assert.equal(normalizeProactive({ minMinutes: 0 }).minMinutes, MIN_ALLOWED_MINUTES);
  assert.equal(normalizeProactive({ minMinutes: 99999 }).minMinutes, MAX_ALLOWED_MINUTES);
  // 上限填得比下限小：抬平，而不是留下一个空区间让随机取值除零。
  const flipped = normalizeProactive({ minMinutes: 120, maxMinutes: 10 });
  assert.equal(flipped.maxMinutes, flipped.minMinutes);
  // 乱填的东西退回默认，而不是变成 NaN 之后让轮询器 sleep(NaN) 永远不醒。
  const junk = normalizeProactive({ minMinutes: "很久", maxMinutes: null, quietStart: 99, quietEnd: -3 });
  assert.equal(junk.minMinutes, PROACTIVE_DEFAULTS.minMinutes);
  assert.equal(junk.quietStart, PROACTIVE_DEFAULTS.quietStart);
  assert.equal(junk.quietEnd, PROACTIVE_DEFAULTS.quietEnd);
  assert.ok(Number.isFinite(rangeFrom(junk).minIntervalMs));
});

test("enabled 只认真正的 true", () => {
  for (const value of ["true", 1, "on", {}, [], "是"]) {
    assert.equal(normalizeProactive({ enabled: value }).enabled, false, `${String(value)} 不算打开`);
  }
  assert.equal(normalizeProactive({ enabled: true }).enabled, true);
});

// ── 静默时段 ────────────────────────────────────────────────

test("跨午夜的静默区间判得对", () => {
  const night = { quietStart: 23, quietEnd: 8 };
  for (const hour of [23, 0, 3, 7]) {
    assert.equal(inQuietHours(night, hour), true, `${hour} 点应当静默`);
    assert.equal(isQuietNow(night, hour), true, `轮询器在 ${hour} 点也应当认为是静默`);
  }
  for (const hour of [8, 12, 22]) {
    assert.equal(inQuietHours(night, hour), false, `${hour} 点不该静默`);
    assert.equal(isQuietNow(night, hour), false);
  }
});

test("不跨午夜的静默区间也判得对", () => {
  const nap = { quietStart: 13, quietEnd: 15 };
  assert.equal(inQuietHours(nap, 13), true);
  assert.equal(inQuietHours(nap, 14), true);
  assert.equal(inQuietHours(nap, 15), false, "结束那一点本身不算静默");
  assert.equal(inQuietHours(nap, 12), false);
});

test("起止填成一样＝全天都可以找我，不是全天静默", () => {
  // 反过来实现的话，主人想"随时都行"却会得到"永远不说话"，而且完全看不出原因。
  for (const hour of [0, 6, 12, 18, 23]) {
    assert.equal(inQuietHours({ quietStart: 9, quietEnd: 9 }, hour), false);
    assert.equal(isQuietNow({ quietStart: 9, quietEnd: 9 }, hour), false);
  }
});

test("轮询器和面板对静默的判断必须完全一致", () => {
  // 两处实现（persona-store 给面板看，poller 自己判）一旦漂移，就会出现
  // "面板显示不打扰、它照样半夜发消息"这种查不出来的问题。
  for (let start = 0; start < 24; start += 1) {
    for (let end = 0; end < 24; end += 3) {
      for (let hour = 0; hour < 24; hour += 1) {
        assert.equal(
          inQuietHours({ quietStart: start, quietEnd: end }, hour),
          isQuietNow({ quietStart: start, quietEnd: end }, hour),
          `start=${start} end=${end} hour=${hour} 两处判断不一致`,
        );
      }
    }
  }
});

// ── 落库 ────────────────────────────────────────────────────

test("主动设置和语气存在同一行，换个实例读得回来", (t) => {
  const spool = openSpool(t);
  const store = new PersonaStore({ database: spool });

  store.write({
    tone: "quiet",
    proactive: { enabled: true, minMinutes: 90, maxMinutes: 300, quietStart: 22, quietEnd: 9 },
  });

  const reread = new PersonaStore({ database: spool }).read();
  assert.equal(reread.tone, "quiet");
  assert.equal(reread.proactive.enabled, true);
  assert.equal(reread.proactive.minMinutes, 90);
  assert.equal(reread.proactive.maxMinutes, 300);
  assert.equal(reread.proactive.quietStart, 22);
  assert.equal(reread.proactive.quietEnd, 9);
});

test("只改语气不会把主动设置弄丢的反面：没给就是回到默认，行为要可预期", (t) => {
  const spool = openSpool(t);
  const store = new PersonaStore({ database: spool });
  store.write({ proactive: { enabled: true, minMinutes: 90 } });
  assert.equal(store.read().proactive.enabled, true);

  // 前端每次都提交整份设置。这条钉住的是行为可预期：整份覆盖时"没给"就是默认，
  // 不会变成"保留上一次"的隐式状态。默认现在是开，所以这里从 false 改成 true——
  // 被钉住的性质没变，变的是默认值。
  store.write({ tone: "plain" });
  assert.equal(store.read().proactive.enabled, true);
  assert.equal(store.read().tone, "plain");
});

// 上面那条整份覆盖的语义，正是窄入口不能用它的原因。
test("窄入口只改主动设置，不碰语气；也不会把已经关掉的人打开", (t) => {
  const spool = openSpool(t);
  const store = new PersonaStore({ database: spool });
  const person = "usr_LK2nQd8w4pXsRt6VbYcH3m";

  store.writeFor(person, { tone: "plain", callMe: "老王", proactive: { enabled: false } });
  assert.equal(store.readFor(person).proactive.enabled, false);

  // 微信里发「别再问我」只知道 enabled 这一个字段。走整份覆盖的话语气和称呼
  // 会被清成默认值——这就是为什么要有 setProactiveFor。
  store.setProactiveFor(person, { enabled: true });
  assert.equal(store.readFor(person).proactive.enabled, true);
  assert.equal(store.readFor(person).tone, "plain", "改主动设置不该动语气");
  assert.equal(store.readFor(person).callMe, "老王", "改主动设置不该动称呼");

  // 反过来：只改语气的窄入口不能把关掉的人重新打开。
  store.setProactiveFor(person, { enabled: false });
  store.setProactiveFor(person, { minMinutes: 90 });
  assert.equal(store.readFor(person).proactive.enabled, false, "没给 enabled 就不该动它");
  assert.equal(store.readFor(person).proactive.minMinutes, 90);
});

test("没自己那一行的人，主动设置用默认值，不跟着主人走", (t) => {
  const spool = openSpool(t);
  const store = new PersonaStore({ database: spool });
  // 主人把自己的关了，并且调成很密。
  store.write({ tone: "warm", proactive: { enabled: false, minMinutes: 10, maxMinutes: 20 } });

  const stranger = store.readFor("usr_Zx9Qw2Er4Ty6Ui8Op0As1D");
  // 语气继承主人（他设的是所有人的默认口吻）……
  assert.equal(stranger.tone, "warm");
  // ……但主动找我不继承：默认开着、默认频率。
  assert.equal(stranger.proactive.enabled, true, "主人关掉自己的，不该把所有人一起关掉");
  assert.equal(stranger.proactive.minMinutes, PROACTIVE_DEFAULTS.minMinutes);
});

// ── 频率换算 ────────────────────────────────────────────────

test("分钟换成毫秒，且最短不低于一分钟", () => {
  assert.deepEqual(rangeFrom({ minMinutes: 45, maxMinutes: 240 }), {
    minIntervalMs: 45 * 60_000,
    maxIntervalMs: 240 * 60_000,
  });
  // 就算上游漏了归一化，轮询器自己也不能变成忙等。
  const floor = rangeFrom({ minMinutes: 0, maxMinutes: 0 });
  assert.ok(floor.minIntervalMs >= 60_000, "最短间隔不得低于一分钟");
  assert.ok(floor.maxIntervalMs >= floor.minIntervalMs);
});

// ── context_token：主动消息能不能发出去，全看这一条 ─────────
//
// 这是本仓第七次"代码存在但真实链路走不到"。往 channelAdapter 的 context_token
// 缓存里写的只有 rememberBaselineStagingContextTokens，而它只在**非 durable**
// 那条分支上被调用；线上跑的是 durable 那条，于是缓存永远是空的：
//   · cyberboss_reminder_create 一律抛 "Let this user talk to the bot once
//     first"，哪怕这个人刚刚说完话
//   · 主动打招呼能唤醒模型，但答复没有投递目标，发不出去
// 生产上 accounts/ 目录里连 .context-tokens.json 这个文件都不存在，就是证据。


test("durable 路收下消息时，必须把 context_token 记进渠道缓存", () => {
  // 直接钉住线上那条分支的接线。onAccepted 是唯一同时握着 senderId 和
  // context_token 的地方——去掉自动回执之后它空着，正好用来干这件事。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "core", "app.js"),
    "utf8",
  );
  const hook = source.slice(
    source.indexOf("onAccepted:"),
    source.indexOf("onAccepted:") + 400,
  );
  assert.match(
    hook,
    /rememberContextToken/,
    "durable inbox 收下消息时必须记住 context_token，否则主动消息和提醒都发不出去",
  );
  assert.match(hook, /normalized\.senderId/);
  assert.match(hook, /normalized\.contextToken/);
});

test("记 context_token 失败不得把消息挡在门外", () => {
  // 记不住最坏是主动消息暂时发不出去；让它把整条来信挡下来就是本末倒置。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "core", "app.js"),
    "utf8",
  );
  const start = source.indexOf("onAccepted: ({ normalized })");
  assert.ok(start > 0, "onAccepted 必须是那个记 token 的形状");
  const hook = source.slice(start, start + 420);
  assert.match(hook, /try\s*\{/, "记不住要吞掉，不能往上抛");
  assert.match(hook, /catch/);
});

test("真的调得到：渠道适配器上确实有 rememberContextToken 这个方法", () => {
  // 上面两条扫的是接线，这条确认被调的那个名字真的存在——名字打错了
  // 上面照样能通过，而线上会静默什么都不做（?. 会把它吞掉）。
  const adapterSource = fs.readFileSync(
    path.join(__dirname, "..", "src", "adapters", "channel", "weixin", "index.js"),
    "utf8",
  );
  assert.match(
    adapterSource,
    /^\s{4}rememberContextToken,\s*$/m,
    "weixin 适配器必须把 rememberContextToken 导出到返回的对象上",
  );
});

test("重启之后不能等人先说话——启动时要把会话上下文补回来", () => {
  // onAccepted 只在新消息进来时记。光有它的话，每次部署重启缓存又空了，主动
  // 打招呼要等有人先说一句才发得出去——而"主动"的意思恰恰是不等人先说话。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "core", "app.js"),
    "utf8",
  );
  assert.match(source, /backfillContextTokensFromInbox\(\)/, "启动流程里必须调这个补回");
  const boot = source.indexOf("this.backfillContextTokensFromInbox()");
  const loopStarted = source.indexOf("bridge loop started");
  assert.ok(boot > 0 && boot < loopStarted, "补回必须排在轮询启动之前");
});

// ── F7 主人自 7-29 起收不到任何主动消息 ─────────────────

test("F7 老格式留下的 __owner__ 排期要认，且认过就换成真实 senderId", async () => {
  // 生产上的真实故障：next-checkin.json 里主人那条存在 __owner__ 名下（旧版
  // 单值文件迁移时写的），而轮询循环按**真实 senderId** 查表——两边对不上，
  // 于是每一轮都走「没排过」重掷一次，一次都发不出去。
  //
  // 主人因此从 2026-07-29 起再没收到过任何主动消息，而日志里只有一句
  // 「轮询器已启动（当前开着）」。「开着」和「有目标」是两回事。
  const fs = require("node:fs");
  const os = require("node:os");
  const path = require("node:path");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb-checkin-"));
  const file = path.join(dir, "next-checkin.json");
  try {
    // 老格式：只有一个数字。
    const legacyDue = Date.now() - 60_000;
    fs.writeFileSync(file, JSON.stringify({ nextAtMs: legacyDue }));

    const source = fs.readFileSync(
      path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8");
    // 循环里必须认这个旧键，否则主人那条永远读不到。
    assert.ok(source.includes("schedule.__owner__"),
      "循环里不认 __owner__——主人那条排期永远读不到，一次都发不出去");
    // 而且认过之后要换成真实 senderId 并把旧键删掉：留着的话每次重启都要再
    // 兼容一次，而兼容层活得越久越没人记得它为什么在。
    const at = source.indexOf("schedule.__owner__");
    const after = source.slice(at, at + 400);
    assert.ok(after.includes("nextCheckinStore.write(target.senderId"),
      "认了旧键但没换成真实 senderId");
    assert.ok(after.includes('forget("__owner__")'), "认了旧键但没把它删掉");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("F7 认不出主人时要出声，不能静默跳过", () => {
  // 静默返回空串的后果是 listCheckinTargets 把主人整个跳过——他从此收不到
  // 任何主动消息，而面板和日志都只说「轮询器开着」。
  // 生产上这件事发生了，没有任何人发现。
  const fs = require("node:fs");
  const path = require("node:path");
  const app = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  const start = app.indexOf("  resolveOwnerSenderIdForCheckin() {");
  const body = app.slice(start, app.indexOf("\n  }", app.indexOf("return \"\";", start)));
  assert.ok(/console\.warn/.test(body),
    "认不出主人时一声不吭——这正是它静默了三天没人发现的原因");
});
