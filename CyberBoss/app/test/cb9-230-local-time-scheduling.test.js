"use strict";

// CB9-230 提醒、安静时段、自然语言时间切到用户当地时区（AC-011 / AC-016）
//
//   AC-011 设置 Australia/Sydney 与 America/New_York，假时钟触发提醒/安静时段；
//          当地行为正确且审计仍按北京时间。
//   AC-016 Fake Clock 覆盖悉尼和纽约 DST 跳时/重复时；不存在的时间请求确认，
//          重复的时间显示偏移并记录选择。
//
// 这一节点改的是**谁的时区**。改之前所有人共用 OWNER_TIMEZONE：一个在悉尼的
// 人说「明天下午三点提醒我」，会被建成北京时间的下午三点——他那边是晚上六点，
// 差三小时，而且他没有任何办法发现，直到闹钟在错的时候响。
//
// 假时钟是真的假时钟：所有断言都喂固定的 now，不读系统时间。读系统时间的测试
// 会在某些日期通过、某些日期失败，而失败的那天你会以为是代码坏了。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildConfirmation,
  buildNonexistentTimeQuestion,
  classifyWallClock,
  parseReminderIntent,
} = require("../src/services/reminder/reminder-intent");
const { parseItemIntent } = require("../src/services/items/item-intent");
const { formatInZone, hourInZone } = require("../src/services/time/canonical-time");

const SYDNEY = "Australia/Sydney";
const NEW_YORK = "America/New_York";
const BEIJING = "Asia/Shanghai";

// 2026-07-29 14:48 UTC ＝ 悉尼 30 日 00:48（AEST，+10）＝ 北京 29 日 22:48
//                     ＝ 纽约 29 日 10:48（EDT，−4）
const NOW = Date.parse("2026-07-29T14:48:00.000Z");

// ── AC-011 提醒按本人时区解析 ──────────────────────────────

test("AC-011 同一句话在不同时区解析出不同的时刻", () => {
  const sydney = parseReminderIntent("明天下午三点提醒我吃药", { now: NOW, timeZone: SYDNEY });
  const beijing = parseReminderIntent("明天下午三点提醒我吃药", { now: NOW, timeZone: BEIJING });
  assert.ok(sydney && beijing);
  assert.notEqual(sydney.dueAtMs, beijing.dueAtMs,
    "两个时区解析出了同一个瞬时——说明时区参数根本没起作用");

  // 悉尼那位说的「明天下午三点」，就是悉尼墙上时间的 15:00。
  assert.equal(formatInZone(sydney.dueAtMs, SYDNEY), "2026-07-31 15:00");
  // 北京这位说的同一句话，是北京墙上时间的 15:00。
  assert.equal(formatInZone(beijing.dueAtMs, BEIJING), "2026-07-30 15:00");
});

test("AC-011 纽约那位说「明天早上八点」，落在纽约的早上八点", () => {
  const intent = parseReminderIntent("明天早上八点提醒我开会", { now: NOW, timeZone: NEW_YORK });
  assert.ok(intent);
  assert.equal(formatInZone(intent.dueAtMs, NEW_YORK), "2026-07-30 08:00");
  // 审计口径仍是北京时间：同一个瞬时在北京是 20:00（EDT 是 UTC−4，差 12 小时）。
  assert.equal(formatInZone(intent.dueAtMs, BEIJING), "2026-07-30 20:00");
});

test("AC-011 相对时间不受时区影响——「10 分钟后」在哪儿都是 10 分钟后", () => {
  // 这条是反面：不是所有东西都该跟着时区变。把相对时间也按时区换算是一类
  // 常见的过度修正，表现是「10 分钟后提醒我」在跨时区的人那里延后了 8 小时。
  for (const zone of [SYDNEY, NEW_YORK, BEIJING]) {
    const intent = parseReminderIntent("10分钟后提醒我喝水", { now: NOW, timeZone: zone });
    assert.equal(intent.dueAtMs, NOW + 10 * 60_000, `${zone} 把相对时间也换算了`);
  }
});

test("AC-011 待办/日程的开始时刻同样按本人时区", () => {
  const sydney = parseItemIntent("安排 明天下午三点 见客户", { now: NOW, timeZone: SYDNEY });
  const beijing = parseItemIntent("安排 明天下午三点 见客户", { now: NOW, timeZone: BEIJING });
  if (sydney?.dueAt && beijing?.dueAt) {
    assert.notEqual(sydney.dueAt, beijing.dueAt, "日程没跟着本人时区走");
    assert.equal(formatInZone(sydney.dueAt, SYDNEY).slice(11), "15:00");
  } else {
    // 这句话不归确定性口令管（交给模型）——那也行，但两边必须一致，
    // 不能一个认一个不认。
    assert.equal(Boolean(sydney), Boolean(beijing));
  }
});

// ── AC-041 双时间文案（CB9-200 留的那半条）────────────────

test("AC-041 跨时区的提醒确认同时显示当地时间和北京时间", () => {
  const intent = parseReminderIntent("明天下午三点提醒我吃药", { now: NOW, timeZone: SYDNEY });
  const reply = buildConfirmation(intent);
  // 当地时间在前——那是他说的那个点。
  assert.match(reply, /15:00/);
  // 北京时间也在，否则他和主人约的「明天 15:00」是两个时刻，而两边都以为对上了。
  assert.match(reply, /北京时间/);
  assert.match(reply, /13:00/, "北京时间那半句算错了（AEST 是 UTC+10，比北京早 2 小时）");
});

test("AC-041 本人就在北京时只显示一次", () => {
  const intent = parseReminderIntent("明天下午三点提醒我吃药", { now: NOW, timeZone: BEIJING });
  const reply = buildConfirmation(intent);
  assert.ok(!reply.includes("北京时间"), `北京用户看到了多余的括号：${reply}`);
  assert.match(reply, /15:00/);
});

test("AC-041 墙上时间和北京相同的时区也折叠", () => {
  const intent = parseReminderIntent("明天下午三点提醒我吃药", { now: NOW, timeZone: "Asia/Chongqing" });
  const reply = buildConfirmation(intent);
  assert.ok(!reply.includes("北京时间"), `重庆用户看到了纯噪声：${reply}`);
});

// ── AC-016 DST ────────────────────────────────────────────

test("AC-016 不存在的时刻不建闹钟，去问一句", () => {
  // 2026-10-04 悉尼 02:00 跳到 03:00，那一小时不存在。
  // 第一版实现在这里安静地给了 01:00——早一小时，而用户没有任何办法发现，
  // 直到闹钟在错的时候响。「不存在就悄悄挪」是这条 AC 真正要挡的东西，
  // 所以断言必须钉住 needsConfirmation，而不只是「渲染出来不是 02:xx」
  // ——后者对那个早一小时的错误答案同样成立。
  const before = Date.parse("2026-10-03T13:00:00.000Z"); // 悉尼 3 日 23:00
  const intent = parseReminderIntent("明天凌晨两点提醒我", { now: before, timeZone: SYDNEY });
  assert.ok(intent, "整句被丢掉了——用户什么反馈都收不到");
  assert.equal(intent.needsConfirmation, true, "给一个不存在的时刻建了闹钟");
  assert.equal(intent.reason, "nonexistent_local_time");
  assert.equal(intent.askedFor, "02:00");
  assert.equal(intent.dueAtMs, undefined, "既然要问，就不该已经定好时刻");

  const question = buildNonexistentTimeQuestion(intent);
  assert.match(question, /02:00/);
  assert.match(question, /[?？]/);
});

test("AC-016 同一句话在不跳时的日子照常建，不会被误判", () => {
  // 反面：上一条不能是靠「凌晨两点一律拒绝」通过的。
  const normal = parseReminderIntent("明天凌晨两点提醒我", {
    now: Date.parse("2026-07-29T13:00:00.000Z"), timeZone: SYDNEY,
  });
  assert.ok(normal && !normal.needsConfirmation, "正常日子的凌晨两点也被拒了");
  assert.equal(formatInZone(normal.dueAtMs, SYDNEY).slice(11), "02:00");
});

test("AC-016 重复的时刻取较早那次，并把偏移说出来", () => {
  // 2026-11-01 纽约 02:00 退回 01:00，01:00–02:00 出现两次。
  const before = Date.parse("2026-10-31T23:00:00.000Z"); // 纽约 31 日 19:00
  const intent = parseReminderIntent("明天凌晨一点半提醒我", { now: before, timeZone: NEW_YORK });
  assert.ok(intent && !intent.needsConfirmation);
  assert.equal(intent.ambiguous, true, "没认出这个点当天有两次");
  // 取的是较早那次：EDT，UTC−4。取晚的那次会是 UTC−5，差一小时。
  assert.equal(intent.offsetLabel, "UTC-4");
  assert.equal(new Date(intent.dueAtMs).toISOString(), "2026-11-01T05:30:00.000Z");
  assert.equal(formatInZone(intent.dueAtMs, NEW_YORK).slice(11), "01:30");
  // 回复里必须说清楚是哪一次，否则用户以为的和实际的差一小时，
  // 而两边都觉得自己是对的。
  const reply = buildConfirmation(intent);
  assert.match(reply, /两次/);
  assert.match(reply, /UTC-4/);
});

test("AC-016 fold 检测两个方向都要找——只往一边找会漏掉一半", () => {
  // 悉尼往回拨是 4 月（2026-04-05 02:00→01:00），纽约是 11 月。
  // ownerWallClockToMs 给的可能是较早那次也可能是较晚那次，只往一个方向找
  // 候选就会漏掉一半，而漏掉的那一半表现为 ambiguous=false——看起来像
  // 「这天没问题」。
  const sydney = parseReminderIntent("明天凌晨两点半提醒我", {
    now: Date.parse("2026-04-03T13:00:00.000Z"), timeZone: SYDNEY,
  });
  assert.ok(sydney && sydney.ambiguous, "悉尼 4 月那次重复没认出来");
  assert.equal(sydney.offsetLabel, "UTC+11", "取的不是较早那次");
});

test("AC-016 classifyWallClock 三种结论互斥且都可达", () => {
  const gap = classifyWallClock(
    { year: 2026, month: 10, day: 4, hour: 2, minute: 0 }, SYDNEY);
  assert.equal(gap.kind, "nonexistent");
  const fold = classifyWallClock(
    { year: 2026, month: 11, day: 1, hour: 1, minute: 30 }, NEW_YORK);
  assert.equal(fold.kind, "ambiguous");
  assert.ok(fold.alternateMs > fold.atMs, "alternateMs 应该是较晚那次");
  const ok = classifyWallClock(
    { year: 2026, month: 7, day: 30, hour: 15, minute: 0 }, SYDNEY);
  assert.equal(ok.kind, "ok");
  // 中国不过夏令时，任何一天都不该出现这两种畸形。
  for (const day of [4, 5, 6]) {
    assert.equal(
      classifyWallClock({ year: 2026, month: 4, day, hour: 2, minute: 0 }, BEIJING).kind, "ok");
  }
});

test("AC-016 DST 前后，北京那一侧的偏移量始终是 +8", () => {
  // 中国不过夏令时。悉尼一年切两次，北京一次都不切——所以同一个 UTC 时刻，
  // 北京侧的渲染必须永远是 UTC+8，一分不差。
  for (const iso of [
    "2026-04-04T02:00:00.000Z", // 悉尼退出 AEDT 前
    "2026-04-05T02:00:00.000Z", // 之后
    "2026-10-03T16:00:00.000Z", // 进入 AEDT 前
    "2026-10-04T16:00:00.000Z", // 之后
  ]) {
    const utcHour = new Date(iso).getUTCHours();
    assert.equal(hourInZone(iso, BEIJING), (utcHour + 8) % 24, `${iso} 北京侧偏移不是 +8`);
  }
});

// ── AC-011 安静时段按当地几点 ──────────────────────────────

test("AC-011 安静时段按当地时间判，不是按北京时间", () => {
  // 轮询器里的 isQuietNow 不导出，这里直接验它依赖的那个输入：hourInZone。
  // 一个在纽约的人设「23 点到 8 点别打扰」，按北京时间判的话安静时段会落在
  // 他那边的上午十点到晚上七点——整个白天收不到消息，半夜正好被戳醒。
  const at = "2026-07-29T14:48:00.000Z";
  assert.equal(hourInZone(at, BEIJING), 22);
  assert.equal(hourInZone(at, NEW_YORK), 10, "纽约那位这会儿是上午十点");
  assert.equal(hourInZone(at, SYDNEY), 0, "悉尼那位这会儿是凌晨");

  const quiet = (hour, start = 23, end = 8) =>
    (start < end ? hour >= start && hour < end : hour >= start || hour < end);
  // 同一个瞬时：北京 22 点不算静默，悉尼 0 点算，纽约上午 10 点不算。
  assert.equal(quiet(hourInZone(at, BEIJING)), false);
  assert.equal(quiet(hourInZone(at, SYDNEY)), true, "悉尼那位半夜该被静默");
  assert.equal(quiet(hourInZone(at, NEW_YORK)), false);
});

test("AC-011 轮询器把时区传给了 nowHour——不是自己算一个", () => {
  // 结构性：nowHour 必须**接收**时区参数。不接收的实现（一律北京）在上面那条
  // 逻辑测试里依然全绿，因为那条测的是 hourInZone 不是轮询器。
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "app", "system-checkin-poller.js"), "utf8",
  );
  assert.match(src, /nowHour\(readTimezone\(target\.senderId\)\)/,
    "安静时段没有按目标本人的时区判");
  assert.match(src, /readTimezone/, "没有读时区的注入点");
});
