"use strict";

// CB9-250 Fake Clock、DST、双时间文案与权限拒绝的冻结测试
//                              （AC-010 / AC-012 / AC-016 / AC-041 / AC-042）
//
// 前面五个节点各自证明了自己那一块。这一份不重复它们，它盯的是**只有把 S2 整
// 段放在一起看才成立**的三类性质：
//
//   一、可注入的时钟。前面的测试都喂固定的 now 就通过了——但那只证明「函数
//       接受 now 参数」，不证明生产代码在做时间决策时**用的是那个参数**。
//       一个偷偷调 Date.now() 的分支在所有喂固定值的测试里都是绿的。
//   二、时区遍历。单点断言在 Australia/Sydney 上对，不代表在
//       Asia/Kathmandu（+5:45）或 Pacific/Chatham（+12:45/+13:45）上对。
//       半小时和三刻钟偏移的时区是这类代码最容易崩的地方。
//   三、可追溯。每条 AC 至少被一份带 AC 编号的测试文件覆盖——漏掉一条的表现
//       是「全绿但那条 AC 从来没被验过」。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  BEIJING_ZONE,
  canonicalStamp,
  dualTime,
  formatInZone,
  hourInZone,
  isValidIanaZone,
} = require("../src/services/time/canonical-time");
const {
  classifyWallClock,
  ownerWallClockToMs,
  parseReminderIntent,
} = require("../src/services/reminder/reminder-intent");

const TEST_DIR = __dirname;
const SRC_DIR = path.join(__dirname, "..", "src");

// 覆盖各种偏移形态的时区。整点、半小时、三刻钟、南北半球、过与不过夏令时。
const ZONES = Object.freeze([
  "Asia/Shanghai",        // +8，不过 DST
  "Asia/Tokyo",           // +9，不过 DST
  "Asia/Kolkata",         // +5:30，半小时
  "Asia/Kathmandu",       // +5:45，三刻钟
  "Australia/Adelaide",   // +9:30/+10:30，半小时 + DST
  "Australia/Sydney",     // +10/+11，南半球 DST
  "Pacific/Chatham",      // +12:45/+13:45，三刻钟 + DST
  "Pacific/Auckland",     // +12/+13
  "Europe/London",        // 0/+1
  "Europe/Paris",         // +1/+2
  "America/New_York",     // −5/−4
  "America/St_Johns",     // −3:30/−2:30，半小时负偏移
  "America/Los_Angeles",  // −8/−7
  "Pacific/Kiritimati",   // +14，最东
  "Pacific/Niue",         // −11，最西
  "UTC",
]);

// 一年里散开的瞬时，覆盖两个半球的 DST 切换窗口。
const INSTANTS = Object.freeze([
  "2026-01-01T00:00:00.000Z", "2026-03-08T06:59:00.000Z", "2026-03-08T07:01:00.000Z",
  "2026-03-29T00:59:00.000Z", "2026-03-29T01:01:00.000Z", "2026-04-05T15:59:00.000Z",
  "2026-04-05T16:01:00.000Z", "2026-06-21T12:00:00.000Z", "2026-09-27T13:59:00.000Z",
  "2026-10-03T15:59:00.000Z", "2026-10-04T16:01:00.000Z", "2026-11-01T05:59:00.000Z",
  "2026-11-01T06:01:00.000Z", "2026-12-31T23:59:00.000Z", "2027-02-28T16:00:00.000Z",
]);

// ── 一、时区遍历（AC-010）─────────────────────────────────

test("AC-010 全部时区 × 全部瞬时：四元组始终自洽", () => {
  const bad = [];
  for (const iso of INSTANTS) {
    const stamp = canonicalStamp(iso);
    if (stamp.instant_utc !== new Date(iso).toISOString()) bad.push(`${iso} instant 变了`);
    if (stamp.epoch_ms !== Date.parse(iso)) bad.push(`${iso} epoch 变了`);
    if (stamp.canonical_zone !== BEIJING_ZONE) bad.push(`${iso} 权威口径不是北京`);
    // canonical_beijing 必须能反解回同一个瞬时（差不超过一分钟的精度损失）。
    const back = ownerWallClockToMs({
      year: Number(stamp.canonical_beijing.slice(0, 4)),
      month: Number(stamp.canonical_beijing.slice(5, 7)),
      day: Number(stamp.canonical_beijing.slice(8, 10)),
      hour: Number(stamp.canonical_beijing.slice(11, 13)),
      minute: Number(stamp.canonical_beijing.slice(14, 16)),
    }, BEIJING_ZONE);
    if (Math.abs(back - stamp.epoch_ms) >= 60_000) {
      bad.push(`${iso} 北京时间反解不回来：${stamp.canonical_beijing}`);
    }
  }
  assert.deepEqual(bad, [], bad.join("\n"));
});

test("AC-010 半小时和三刻钟偏移的时区照样对", () => {
  // 整点偏移上写对、非整点上写错，是这类代码最典型的坏法：`hour + offset`
  // 这种实现在 Asia/Shanghai 上永远是绿的。
  const at = "2026-06-21T12:00:00.000Z";
  assert.equal(formatInZone(at, "Asia/Kolkata"), "2026-06-21 17:30");
  assert.equal(formatInZone(at, "Asia/Kathmandu"), "2026-06-21 17:45");
  assert.equal(formatInZone(at, "America/St_Johns"), "2026-06-21 09:30");
  // Chatham 六月是 +12:45（NZST 期间）。
  assert.equal(formatInZone(at, "Pacific/Chatham"), "2026-06-22 00:45");
  // 小时函数在半小时时区上取的是小时位，不是四舍五入。
  assert.equal(hourInZone(at, "Asia/Kathmandu"), 17);
});

test("AC-041 全部时区 × 全部瞬时：折叠规则永远和渲染结果一致", () => {
  const bad = [];
  for (const zone of ZONES) {
    for (const iso of INSTANTS) {
      const t = dualTime(iso, zone);
      const shouldCollapse = t.user_local === formatInZone(iso, BEIJING_ZONE);
      if (t.same_as_beijing !== shouldCollapse) {
        bad.push(`${zone} @ ${iso}: 折叠判断和渲染结果不符`);
      }
      // 折叠时只出现一次「时间」这个词；不折叠时当地和北京都在。
      const times = (t.label.match(/时间/g) || []).length;
      if (shouldCollapse && times !== 1) bad.push(`${zone} @ ${iso}: 折叠了却出现 ${times} 次`);
      if (!shouldCollapse && !t.label.includes("北京时间")) {
        bad.push(`${zone} @ ${iso}: 跨时区却没给北京时间`);
      }
    }
  }
  assert.deepEqual(bad, [], bad.slice(0, 10).join("\n"));
});

test("AC-010 认不出的时区一律回退，遍历一圈不抛", () => {
  for (const junk of ["Mars/Olympus", "", "  ", "Asia//Shanghai", "../../etc/passwd", "A".repeat(200)]) {
    assert.equal(isValidIanaZone(junk), false, `${JSON.stringify(junk)} 被当成了合法时区`);
    assert.doesNotThrow(() => dualTime("2026-06-21T12:00:00.000Z", junk));
    assert.equal(dualTime("2026-06-21T12:00:00.000Z", junk).user_zone, BEIJING_ZONE);
  }
});

// ── 二、DST 遍历（AC-016）──────────────────────────────────

test("AC-016 每个过夏令时的时区，一年里都能找到 gap 和 fold", () => {
  // 这条是**覆盖性**断言：它证明 classifyWallClock 的三种结论在真实时区上都
  // 可达。只在悉尼上测的话，一个「南半球对、北半球反了」的实现是绿的。
  const DST_ZONES = ["Australia/Sydney", "America/New_York", "Europe/London", "Pacific/Auckland"];
  for (const zone of DST_ZONES) {
    const kinds = new Set();
    for (let month = 1; month <= 12; month += 1) {
      for (let day = 1; day <= 31; day += 1) {
        // 现实里所有 DST 切换都发生在当地 0–3 点。扫全天是 4 倍的开销换零信息。
        for (const hour of [0, 1, 2, 3]) {
          for (const minute of [0]) {
            let result;
            try {
              result = classifyWallClock({ year: 2026, month, day, hour, minute }, zone);
            } catch {
              continue; // 不存在的日期（2 月 30 日之类）
            }
            kinds.add(result.kind);
          }
        }
      }
    }
    assert.ok(kinds.has("nonexistent"), `${zone} 一年里找不到跳时——检测多半反了`);
    assert.ok(kinds.has("ambiguous"), `${zone} 一年里找不到重复时`);
    assert.ok(kinds.has("ok"), `${zone} 连正常时刻都没有，那就是全判错了`);
  }
});

test("AC-016 不过夏令时的时区，一年里一个 gap 一个 fold 都不该有", () => {
  // 反面。误报的后果是这些地方的人每年被问几次莫名其妙的问题。
  for (const zone of [BEIJING_ZONE, "Asia/Tokyo", "Asia/Kolkata", "UTC"]) {
    const weird = [];
    for (let month = 1; month <= 12; month += 1) {
      // 只扫 DST 会切的那几个月 + 每月前 7 天和月末那周：误报如果存在，
      // 一定出现在切换窗口附近，全年全天扫是 10 倍开销换同一个结论。
      for (const day of [1, 2, 3, 4, 5, 6, 7, 25, 26, 27, 28]) {
        for (const hour of [0, 1, 2, 3]) {
          const result = classifyWallClock({ year: 2026, month, day, hour, minute: 0 }, zone);
          if (result.kind !== "ok") {
            weird.push(`${zone} ${month}-${day} ${hour}:00 → ${result.kind}`);
          }
        }
      }
    }
    assert.deepEqual(weird, [], weird.slice(0, 5).join("\n"));
  }
});

// ── 三、假时钟真的能注入 ──────────────────────────────────

test("AC-016 时间决策全部走注入的 now——冻结系统时钟也不影响结果", () => {
  // 把 Date.now 和 Date 构造整个换掉。任何偷偷读系统时钟的分支在这里会得到
  // 一个荒谬的年份，结果必然不同；而喂固定 now 的普通测试对它是绿的。
  const realNow = Date.now;
  const RealDate = Date;
  const FIXED = Date.parse("2026-07-29T14:48:00.000Z");
  const results = [];
  for (const frozen of ["1999-01-01T00:00:00.000Z", "2099-12-31T23:59:00.000Z"]) {
    const frozenMs = Date.parse(frozen);
    try {
      // eslint-disable-next-line no-global-assign
      Date = class extends RealDate {
        constructor(...args) {
          if (args.length === 0) {
            super(frozenMs);
            return;
          }
          super(...args);
        }

        static now() {
          return frozenMs;
        }
      };
      results.push(parseReminderIntent("明天下午三点提醒我吃药", {
        now: FIXED, timeZone: "Australia/Sydney",
      })?.dueAtMs);
    } finally {
      // eslint-disable-next-line no-global-assign
      Date = RealDate;
      Date.now = realNow;
    }
  }
  assert.equal(results[0], results[1],
    "换了系统时钟结果就变了——说明有分支绕过了注入的 now");
  assert.equal(formatInZone(results[0], "Australia/Sydney"), "2026-07-31 15:00");
});

test("AC-016 时间敏感的模块不在决策点直接读系统时钟", () => {
  // 结构性：这几个文件里的 Date.now() / new Date() 必须只出现在**默认参数**
  // 位置（`now = Date.now()`），不能出现在函数体内的判断里。
  // 出现在函数体里就意味着那条路没法用假时钟测，而没法测的路就是没测的路。
  const FILES = [
    "services/reminder/reminder-intent.js",
    "services/location/location-profile.js",
    "services/time/canonical-time.js",
  ];
  const offenders = [];
  for (const rel of FILES) {
    const lines = fs.readFileSync(path.join(SRC_DIR, rel), "utf8").split("\n");
    lines.forEach((line, i) => {
      const code = line.replace(/\/\/.*$/, "");
      if (!/Date\.now\(\)|new Date\(\)/.test(code)) return;
      // 允许：默认参数（含 `= new Date()`、`= Date.now()`）和 canonicalStamp
      // 这类「不给参数就取现在」的入口。
      if (/=\s*(Date\.now\(\)|new Date\(\))/.test(code)) return;
      offenders.push(`${rel}:${i + 1}  ${line.trim()}`);
    });
  }
  assert.deepEqual(offenders, [],
    `这些地方在函数体里直接读了系统时钟，假时钟测不到：\n${offenders.join("\n")}`);
});

// ── 四、权限拒绝（AC-042）─────────────────────────────────

test("AC-042 整个 web 层没有任何会弹权限框的调用", () => {
  // CB9-210 只扫了加入页。这一条扫**所有**模板：以后新加一页也在守卫范围里。
  const templatesDir = path.join(__dirname, "..", "templates");
  const PROMPTS = ["geolocation", "getCurrentPosition", "watchPosition",
    "permissions.query", "requestPermission", "getUserMedia", "requestMIDIAccess"];
  const offenders = [];
  for (const name of fs.readdirSync(templatesDir)) {
    if (!name.endsWith(".html")) continue;
    const code = fs.readFileSync(path.join(templatesDir, name), "utf8")
      .replace(/<!--[\s\S]*?-->/g, "")
      .split("\n")
      .map((line) => line.replace(/(^|[^:])\/\/.*$/, "$1"))
      .join("\n");
    for (const call of PROMPTS) {
      if (code.includes(call)) offenders.push(`${name}: ${call}`);
    }
  }
  assert.deepEqual(offenders, [], `这些页面会弹权限框：\n${offenders.join("\n")}`);
});

test("AC-042 服务端也没有任何处理精确坐标的入口", () => {
  // 前端不弹框，但后端如果留着一个收经纬度的接口，AC-013 的硬门就只剩一层。
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
      const text = fs.readFileSync(full, "utf8");
      // FORBIDDEN_FIELDS 那张表本身会提到这些词，它是**挡**它们的，不算违规。
      if (full.endsWith(path.join("location", "timezone-signals.js"))) continue;
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        const code = line.replace(/\/\/.*$/, "");
        // 找的是「从请求里取经纬度」这种形状，不是任何提到 latitude 的字符串。
        if (/body\??\.(latitude|longitude|coords)|req(uest)?\??\.(body|query)\??\.(lat|lng|latitude|longitude)/.test(code)) {
          offenders.push(`${path.relative(SRC_DIR, full)}:${i + 1}`);
        }
      });
    }
  };
  walk(SRC_DIR);
  assert.deepEqual(offenders, [], `这些地方在收精确坐标：\n${offenders.join("\n")}`);
});

// ── 五、可追溯 ────────────────────────────────────────────

test("S2 每条 AC 都至少有一份带编号的测试覆盖", () => {
  // 漏掉一条的表现是「全绿但那条 AC 从来没被验过」——而 traceability 表上它
  // 依然写着某个节点负责。这条把「谁负责」和「谁真的测了」对上。
  const S2_ACS = ["AC-010", "AC-011", "AC-012", "AC-013", "AC-014", "AC-015", "AC-016", "AC-041", "AC-042"];
  const corpus = fs.readdirSync(TEST_DIR)
    .filter((name) => name.startsWith("cb9-2") && name.endsWith(".test.js"))
    .concat(["cb9-250-fake-clock-frozen.test.js"])
    .map((name) => fs.readFileSync(path.join(TEST_DIR, name), "utf8"))
    .join("\n");
  const missing = S2_ACS.filter((ac) => !corpus.includes(`${ac} `));
  assert.deepEqual(missing, [], `这些 AC 在 S2 的测试里一次都没被点名：${missing.join(", ")}`);
});

test("S2 的五个节点每个都留了证据目录", () => {
  const evidenceRoot = path.join(__dirname, "..", "..", "docs", "evidence");
  const missing = ["CB9-200", "CB9-210", "CB9-220", "CB9-230", "CB9-240"]
    .filter((node) => {
      const dir = path.join(evidenceRoot, node);
      return !fs.existsSync(dir) || fs.readdirSync(dir).length === 0;
    });
  assert.deepEqual(missing, [], `这些节点没有证据：${missing.join(", ")}`);
});
