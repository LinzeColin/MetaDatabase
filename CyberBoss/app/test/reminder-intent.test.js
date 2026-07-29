"use strict";

// 「我跟他说 1 分钟后提醒我 他没有回话 1 分钟后也没有提醒我」
//
// reminder-queue.json 当时是 {"reminders": []}——模型一次都没调那个工具。
// 说明书里写着「要主动建提醒」，工具也挂着，但**模型没调就是没建**。
// 这一层把这句话从"希望模型愿意"变成"代码必然执行"。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildConfirmation,
  buildDueMessage,
  parseReminderIntent,
} = require("../src/services/reminder/reminder-intent");

// 主人当地 2026-07-29 15:20（北京），也就是 UTC 07:20。
const NOW = Date.parse("2026-07-29T07:20:00.000Z");
const TZ = "Asia/Shanghai";

function parse(text, now = NOW) {
  return parseReminderIntent(text, { now, timeZone: TZ });
}

function minutesFromNow(intent, now = NOW) {
  return Math.round((intent.dueAtMs - now) / 60_000);
}

// ── 主人真正打出来的那句话 ──────────────────────────────────

test("「1分钟后提醒我」——就是这一句让他等了一场空", () => {
  const intent = parse("1分钟后提醒我");

  assert.ok(intent, "这句话解析不出来，整件事就还是靠模型的心情");
  assert.equal(minutesFromNow(intent), 1);
  assert.equal(intent.body, "");
  assert.equal(intent.dueAtLabel, "15:21");
});

test("带内容的：「10分钟后提醒我喝水」", () => {
  const intent = parse("10分钟后提醒我喝水");

  assert.equal(minutesFromNow(intent), 10);
  assert.equal(intent.body, "喝水");
  assert.equal(buildConfirmation(intent), "好，15:30 提醒你喝水。");
  assert.equal(buildDueMessage(intent), "到点了，喝水。");
});

test("没内容的时候，确认和到点那两句都不能空着", () => {
  const intent = parse("1分钟后提醒我");

  assert.equal(buildConfirmation(intent), "好，15:21 叫你一声。");
  assert.equal(buildDueMessage(intent), "到点了，你让我这个时候叫你一声。");
});

// ── 各种说法都要认 ──────────────────────────────────────────

test("中文数字、半小时、个小时、以后——都是常说的", () => {
  for (const [text, expectedMinutes] of [
    ["十分钟后提醒我", 10],
    ["二十分钟后叫我", 20],
    ["半小时后提醒我起来动一动", 30],
    ["两个小时后提醒我", 120],
    ["三小时以后提醒我吃药", 180],
    ["1小时之后叫我", 60],
    ["５分钟后提醒我", 5],
  ]) {
    const intent = parse(text);
    assert.ok(intent, `「${text}」没认出来`);
    assert.equal(minutesFromNow(intent), expectedMinutes, `「${text}」算错了`);
  }
});

test("动词在前也认：「提醒我5分钟后喝水」", () => {
  const intent = parse("提醒我5分钟后喝水");

  assert.equal(minutesFromNow(intent), 5);
  assert.equal(intent.body, "喝水");
});

// ── 几点几分：错 8 小时会把他半夜叫醒 ──────────────────────

test("「明天早上8点叫我起床」按主人的当地时间算，不是 UTC", () => {
  const intent = parse("明天早上8点叫我起床");

  // 北京 7/30 08:00 = UTC 7/30 00:00。
  assert.equal(new Date(intent.dueAtMs).toISOString(), "2026-07-30T00:00:00.000Z");
  assert.equal(intent.dueAtLabel, "明天 08:00");
  assert.equal(intent.body, "起床");
});

test("「下午5点」是 17 点，不是凌晨 5 点", () => {
  const intent = parse("下午5点提醒我打电话");

  // 当地 17:00 = UTC 09:00。认成凌晨 5 点的话，主人会在睡梦里被戳。
  assert.equal(new Date(intent.dueAtMs).toISOString(), "2026-07-29T09:00:00.000Z");
  assert.equal(intent.dueAtLabel, "17:00");
  assert.equal(intent.body, "打电话");
});

test("「晚上8点」是 20 点；「凌晨1点」还是 1 点", () => {
  assert.equal(parse("晚上8点提醒我").dueAtLabel, "20:00");
  assert.equal(parse("凌晨1点提醒我").dueAtLabel, "明天 01:00");
});

test("今天已经过了的钟点，落到明天", () => {
  // 现在是当地 15:20，说「8点提醒我」只可能是明天早上。
  const intent = parse("8点提醒我开会");

  assert.equal(intent.dueAtLabel, "明天 08:00");
});

test("今天还没到的钟点，就是今天", () => {
  const intent = parse("晚上9点提醒我洗澡");

  assert.equal(intent.dueAtLabel, "21:00");
  assert.equal(intent.body, "洗澡");
});

test("「3点半」「后天10点」也要认", () => {
  // 现在是当地 15:20，15:30 还没到，所以就是今天。
  assert.equal(parse("下午3点半提醒我").dueAtLabel, "15:30");
  assert.equal(parse("后天10点提醒我交房租").dueAtLabel, "7 月 31 日 10:00");
  assert.equal(parse("21:30提醒我吃药").dueAtLabel, "21:30");
});

// ── 不该认的，一个都不能认 ────────────────────────────────
//
// 误判比漏判贵得多：把闲聊听成闹钟，主人会在莫名其妙的时间被戳一下，
// 而且他根本不知道那是哪来的。漏判最多是退回原来的行为（模型接着聊）。

test("只有时间没有「提醒」，不建", () => {
  for (const text of [
    "我三点才下班",
    "明天早上8点的高铁",
    "等两个小时后再说吧",
    "十分钟后我就到了",
    "现在几点",
  ]) {
    assert.equal(parse(text), null, `「${text}」被当成闹钟了`);
  }
});

test("只有「提醒」没有时间，不建——交给模型去问清楚", () => {
  for (const text of [
    "提醒我买菜",
    "记得提醒我",
    "你能提醒我吗",
    "帮我设个闹钟",
  ]) {
    assert.equal(parse(text), null, `「${text}」没有时间，不该自己瞎定一个`);
  }
});

test("很短的也认——说了三十秒就是三十秒", () => {
  // 一开始我把下限定在一分钟，理由是"太近了送不准"。但那正是这次要修的病：
  // 主人说了一句明确的话，系统自己判断"这个不值得做"，然后什么都不发生。
  // 到期扫描每一轮都跑，长轮询见到有提醒待发会压到 2 秒，十秒的精度是有的。
  const intent = parse("30秒后提醒我");

  assert.ok(intent, "「30秒后提醒我」也是人话");
  assert.equal(Math.round((intent.dueAtMs - NOW) / 1000), 30);
});

test("送不到的和荒唐的不建", () => {
  // 5 秒后——一次投递都不一定来得及，别答应做不到的事。
  assert.equal(parse("5秒后提醒我"), null);
  // 一年以外的不接。
  assert.equal(parse("500天后提醒我"), null);
});

test("超长文本不进这条路径——那是在聊天，不是在定闹钟", () => {
  const long = `${"我今天真的很累".repeat(40)}5分钟后提醒我`;
  assert.equal(parse(long), null);
});

test("空的、非字符串的，安静返回 null", () => {
  for (const value of ["", "   ", null, undefined, 42, {}]) {
    assert.equal(parseReminderIntent(value, { now: NOW, timeZone: TZ }), null);
  }
});

// ── 夏令时/时区边界 ────────────────────────────────────────

test("跨零点：当地 23:50 说「20分钟后」落到第二天", () => {
  const lateNight = Date.parse("2026-07-29T15:50:00.000Z"); // 当地 23:50
  const intent = parse("20分钟后提醒我睡觉", lateNight);

  assert.equal(intent.dueAtLabel, "明天 00:10");
  assert.equal(new Date(intent.dueAtMs).toISOString(), "2026-07-29T16:10:00.000Z");
});
