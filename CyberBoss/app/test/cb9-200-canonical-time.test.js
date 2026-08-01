"use strict";

// CB9-200 UTC 瞬时层与北京时间权威表达层（AC-010 / AC-041）
//
//   AC-010 同一事件同时含 instant_utc、epoch_ms、canonical_beijing、
//          canonical_zone=Asia/Shanghai；跨服务排序一致。
//   AC-041 跨时区提醒确认同时显示当地时间与北京时间；用户时区为 Asia/Shanghai
//          时只显示一次。
//
// 这个节点做的是**收敛**：改之前 Asia/Shanghai 硬写在 8 个源文件里，其中 4 份
// 是几乎一样的 Intl.DateTimeFormat。这种重复不会报错，只会在有人改了其中一处
// 之后，让同一个时刻在系统里有两种渲染——而且要等到用户投诉才会发现。
//
// 所以这份测试分两半：
//   前半盯**回归**——收敛后线上那几处输出必须逐字节不变；
//   后半盯**新增语义**——四元组、双时间文案、折叠规则、非法输入的回退。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  BEIJING_ZONE,
  canonicalStamp,
  dualTime,
  formatDateInZone,
  formatInZone,
  hourInZone,
  injectedTimeLine,
  isValidIanaZone,
  normalizeUserZone,
} = require("../src/services/time/canonical-time");

// 2026-07-30 那次故障的时刻。UTC 14:48 = 北京 22:48 = 悉尼 00:48（AEST，UTC+10）。
const INCIDENT = "2026-07-29T14:48:00.000Z";

// ── 回归：收敛前后逐字节一致 ────────────────────────────────

test("AC-010 收敛后的渲染和收敛前那 4 份 formatter 逐字节一致", () => {
  // 被替换掉的那份实现，原样抄在这里当 oracle。
  // 不这样写的话，「收敛没改变行为」就只是一句话——而这正是最容易出错的地方：
  // zh-CN 给的是 2026/07/29，en-CA 给的是 2026-07-29,（带逗号），差一个字符就
  // 是线上所有时间戳的形状变了。
  const legacy = (value, seconds) => new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
    hour12: false,
  }).format(new Date(value)).replace(/\//g, "-");

  const samples = [
    INCIDENT,
    "2026-01-01T00:00:00.000Z",   // 北京 08:00，跨年边界
    "2026-12-31T16:00:00.000Z",   // 北京 次年 00:00，跨年 + 跨天
    "2026-03-08T15:59:59.000Z",   // 北美 DST 切换那天——中国不切，结果必须不受影响
    "1999-02-28T16:00:00.000Z",   // 北京 03-01 00:00，闰年前一年的月末
  ];
  for (const iso of samples) {
    for (const seconds of [false, true]) {
      assert.equal(
        formatInZone(iso, BEIJING_ZONE, { seconds }),
        legacy(iso, seconds),
        `${iso} seconds=${seconds} 渲染变了`,
      );
    }
  }
});

test("AC-010 Asia/Shanghai 这个字面量只允许出现在权威层里", () => {
  // 散在八个文件里的时候，改一处漏七处；漏掉的那处不会报错，只会安静地按另
  // 一个时区渲染。这条是**结构性**的防线：新加一处硬编码就红。
  const srcDir = path.join(__dirname, "..", "src");
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "v8-prebuilt") continue;
        walk(full);
        continue;
      }
      if (!entry.name.endsWith(".js")) continue;
      if (full.endsWith(path.join("services", "time", "canonical-time.js"))) continue;
      const lines = fs.readFileSync(full, "utf8").split("\n");
      lines.forEach((line, i) => {
        // 注释里提「默认 Asia/Shanghai」是允许的，代码里写死不行。
        const code = line.replace(/\/\/.*$/, "");
        if (code.includes("Asia/Shanghai")) {
          offenders.push(`${path.relative(srcDir, full)}:${i + 1}`);
        }
      });
    }
  };
  walk(srcDir);
  assert.deepEqual(offenders, [], `这些地方绕过了权威层：\n${offenders.join("\n")}`);
});

// ── AC-010 四元组 ───────────────────────────────────────────

test("AC-010 同一事件一次拿到四个字段", () => {
  const s = canonicalStamp(INCIDENT);
  assert.equal(s.instant_utc, INCIDENT);
  assert.equal(s.epoch_ms, Date.parse(INCIDENT));
  assert.equal(s.canonical_zone, "Asia/Shanghai");
  assert.equal(s.canonical_beijing, "2026-07-29 22:48:00");
  // 冻结：下游改不动其中一个字段，让四个字段互相矛盾。
  assert.ok(Object.isFrozen(s));
});

test("AC-010 跨服务排序一致——按 epoch_ms 和按 canonical_beijing 排出同一个序", () => {
  // 这是分层的**理由**本身。只留表达层的话，跨时区的两条记录会排反；
  // 只留瞬时层的话，人看到的是 UTC。两个都在，且必须同序。
  const instants = [
    "2026-07-29T14:48:00.000Z",
    "2026-07-29T14:47:59.000Z",
    "2026-01-01T00:00:00.000Z",
    "2026-12-31T16:00:00.000Z",
  ].map((iso) => canonicalStamp(iso));

  const byEpoch = [...instants].sort((a, b) => a.epoch_ms - b.epoch_ms).map((s) => s.instant_utc);
  const byBeijing = [...instants]
    .sort((a, b) => a.canonical_beijing.localeCompare(b.canonical_beijing))
    .map((s) => s.instant_utc);
  assert.deepEqual(byBeijing, byEpoch, "两种排序键排出了不同的序");
});

test("AC-010 非法时刻直接抛，不静默给一个看起来对的时间", () => {
  // 悄悄回退成 new Date() 是最坏的处理：调用方拿到一个语法正确的时间戳，
  // 而它指向的是「刚才」而不是那个事件。
  assert.throws(() => canonicalStamp("不是时间"), TypeError);
  assert.throws(() => canonicalStamp(Number.NaN), TypeError);
});

// ── AC-041 双时间文案 ───────────────────────────────────────

test("AC-041 用户在北京时只显示一次时间", () => {
  const t = dualTime(INCIDENT, BEIJING_ZONE);
  assert.equal(t.same_as_beijing, true);
  assert.equal(t.label, "2026-07-29 22:48 北京时间");
  assert.equal((t.label.match(/时间/g) || []).length, 1, "北京用户看到了两遍时间");
});

test("AC-041 跨时区时当地时间和北京时间同时出现", () => {
  const t = dualTime(INCIDENT, "Australia/Sydney");
  assert.equal(t.same_as_beijing, false);
  assert.equal(t.user_local, "2026-07-30 00:48");
  assert.match(t.label, /当地时间/);
  assert.match(t.label, /北京时间 2026-07-29 22:48/);
  // 悉尼那位看到的日期是 30 号——这正是当初报错的那 8 小时，现在两边都写出来了。
  assert.match(t.label, /2026-07-30 00:48/);
});

test("AC-041 和北京同一个墙上时间的时区也折叠", () => {
  // Asia/Chongqing、Asia/Macau 和北京永远是同一个墙上时间。
  // 写成「当地时间 22:48（Asia/Chongqing）｜北京时间 22:48」是纯噪声。
  // 按 zone === 'Asia/Shanghai' 判的实现在这里会红。
  for (const zone of ["Asia/Chongqing", "Asia/Macau", "Asia/Urumqi"]) {
    const t = dualTime(INCIDENT, zone);
    const sameWallClock = t.user_local === "2026-07-29 22:48";
    assert.equal(t.same_as_beijing, sameWallClock,
      `${zone}: 墙上时间${sameWallClock ? "相同" : "不同"}，折叠判断却反了`);
  }
  // Asia/Urumqi 是 UTC+6，墙上时间和北京**不同**——这一条兜住"别把整个中国都
  // 当成东八区"。
  assert.equal(dualTime(INCIDENT, "Asia/Urumqi").same_as_beijing, false);
});

test("AC-041 DST：同一个用户在夏令时前后，北京侧不变而当地侧变", () => {
  // 悉尼 4 月初退出 AEDT（UTC+11 → UTC+10）。北京不过夏令时，所以北京侧那半
  // 句在两次里对同一个 UTC 时刻必须给出同一个偏移。
  const before = dualTime("2026-04-04T02:00:00.000Z", "Australia/Sydney"); // AEDT
  const after = dualTime("2026-04-05T02:00:00.000Z", "Australia/Sydney");  // AEST
  assert.equal(before.user_local, "2026-04-04 13:00", "AEDT 是 UTC+11");
  assert.equal(after.user_local, "2026-04-05 12:00", "AEST 是 UTC+10");
  // 北京侧：两次都是 UTC+8，一小时不多一小时不少。
  assert.equal(before.canonical_beijing, "2026-04-04 10:00:00");
  assert.equal(after.canonical_beijing, "2026-04-05 10:00:00");
});

// ── 外部输入的降级（AC-012 的前置）─────────────────────────

test("认不出来的时区回退北京时间，不抛错", () => {
  // 时区从浏览器上报和 Cloudflare 头里来，都是外部输入。为一个歪掉的时区名让
  // 整条回复失败，是拿主路径去赌一个可以安全降级的字段。
  assert.equal(isValidIanaZone("Mars/Olympus"), false);
  assert.equal(normalizeUserZone("Mars/Olympus"), BEIJING_ZONE);
  assert.equal(normalizeUserZone(""), BEIJING_ZONE);
  assert.equal(normalizeUserZone(null), BEIJING_ZONE);
  assert.equal(normalizeUserZone("A".repeat(500)), BEIJING_ZONE);
  assert.equal(dualTime(INCIDENT, "Mars/Olympus").label, "2026-07-29 22:48 北京时间");
});

test("时区校验的结果被缓存，但缓存不会把有效和无效搞混", () => {
  // 缓存是为了别在每条入站消息上重建 Intl；写错的话会让第二次查询拿到上一个
  // 时区的结论。连着交替查两个，任何按 key 覆盖的实现都会在这里红。
  for (let i = 0; i < 3; i += 1) {
    assert.equal(isValidIanaZone("Australia/Sydney"), true);
    assert.equal(isValidIanaZone("Mars/Olympus"), false);
    assert.equal(isValidIanaZone("Asia/Tokyo"), true);
  }
});

// ── 派生用法 ────────────────────────────────────────────────

test("安静时段读的是北京时间的几点，不是宿主机的", () => {
  // 机器在 UTC 上跑的时候，Date#getHours 会让「23 点静默」在北京时间早上 7 点
  // 生效——这个仓的机器就是 UTC 的。
  assert.equal(hourInZone("2026-07-29T14:48:00.000Z", BEIJING_ZONE), 22);
  assert.equal(hourInZone("2026-07-29T16:00:00.000Z", BEIJING_ZONE), 0, "北京 0 点");
  assert.equal(hourInZone("2026-07-29T15:00:00.000Z", "Australia/Sydney"), 1);
});

test("日记按天归档，天的边界按时区切", () => {
  // 北京 00:30 写的东西属于当天。按 UTC 切会掉进前一天那一篇里。
  assert.equal(formatDateInZone("2026-07-29T16:30:00.000Z", BEIJING_ZONE), "2026-07-30");
  assert.equal(formatDateInZone("2026-07-29T15:30:00.000Z", BEIJING_ZONE), "2026-07-29");
});

test("注入行两条路共用同一个函数，措辞不会飘", () => {
  assert.equal(injectedTimeLine(INCIDENT), "[2026-07-29 22:48 北京时间]");
  assert.equal(injectedTimeLine(INCIDENT, "Australia/Sydney"),
    "[2026-07-30 00:48 Australia/Sydney 当地时间（北京时间 2026-07-29 22:48）]");
  // 拿不到时刻就整行不写，而不是写一个空括号。
  assert.equal(injectedTimeLine("不是时间"), "");
  assert.equal(injectedTimeLine(""), "");
});
