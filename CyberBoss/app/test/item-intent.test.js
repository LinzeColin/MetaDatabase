"use strict";

// 待办和日程的口令层。和提醒同一个道理：模型没调工具就是没建。
//
// 待办比提醒更不能靠运气——提醒漏了主人当场就发现，待办漏了他可能一周后才想起
// 「我不是记过吗」。

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildAddedMessage,
  buildDoneFailedMessage,
  buildDoneMessage,
  buildListMessage,
  parseItemIntent,
} = require("../src/services/items/item-intent");

const NOW = Date.parse("2026-07-29T07:20:00.000Z"); // 当地 15:20
const TZ = "Asia/Shanghai";

function parse(text) {
  return parseItemIntent(text, { now: NOW, timeZone: TZ });
}

// ── 加 ──────────────────────────────────────────────────────

test("「记一下 买菜」记成待办", () => {
  assert.deepEqual(parse("记一下 买菜"), {
    action: "add", kind: "todo", title: "买菜",
  });
});

test("几种说法都认，口令越短越好", () => {
  for (const text of ["记一下 买菜", "待办 买菜", "加待办 买菜", "记下来：买菜", "记一笔 买菜"]) {
    const intent = parse(text);
    assert.equal(intent?.action, "add", `「${text}」没认出来`);
    assert.equal(intent.title, "买菜");
  }
});

test("带时间的记成日程，时间按主人的当地时区算", () => {
  const intent = parse("记一下 明天下午3点开会");

  assert.equal(intent.action, "add");
  assert.equal(intent.kind, "event", "带了明确时刻的是日程，不是待办");
  assert.equal(intent.title, "开会");
  // 北京 7/30 15:00 = UTC 7/30 07:00。错 8 小时会让他错过这个会。
  assert.equal(new Date(intent.dueAtMs).toISOString(), "2026-07-30T07:00:00.000Z");
  assert.equal(intent.dueAtLabel, "明天 15:00");
});

test("没有时间的就是待办，不要自己编一个截止时间", () => {
  const intent = parse("记一下 有空把厨房收拾了");

  assert.equal(intent.kind, "todo");
  assert.equal(intent.dueAtMs, undefined);
});

// ── 看 ──────────────────────────────────────────────────────

test("「待办」「日程」这两个字本身就是查看", () => {
  assert.deepEqual(parse("待办"), { action: "list", kind: "todo" });
  assert.deepEqual(parse("我的待办"), { action: "list", kind: "todo" });
  assert.deepEqual(parse("日程"), { action: "list", kind: "event" });
  assert.deepEqual(parse("日历"), { action: "list", kind: "event" });
});

test("「待办」后面跟了内容就是加，不是看", () => {
  assert.equal(parse("待办 买菜").action, "add");
});

// ── 划掉 ────────────────────────────────────────────────────

test("「完成 1」按列表上的序号划——不能让他打一串十六进制", () => {
  assert.deepEqual(parse("完成 1"), { action: "done", kind: "todo", ordinal: 1 });
  assert.deepEqual(parse("做完了2"), { action: "done", kind: "todo", ordinal: 2 });
  assert.deepEqual(parse("划掉 3"), { action: "done", kind: "todo", ordinal: 3 });
});

test("光说「完成」也认，上层遇到只有一条时直接划掉那条", () => {
  assert.deepEqual(parse("完成"), { action: "done", kind: "todo", ordinal: null });
});

// ── 不该认的 ────────────────────────────────────────────────

test("普通聊天不能被吃掉", () => {
  for (const text of [
    "今天好累",
    "你在吗",
    "我完成了那个项目",
    "这个日程安排得太满了吧",
    "帮我看看这段代码",
  ]) {
    assert.equal(parse(text), null, `「${text}」被当成待办命令了`);
  }
});

test("空的、超长的、非字符串的都返回 null", () => {
  for (const value of ["", "   ", null, undefined, 42, {}, `记一下 ${"啊".repeat(400)}`]) {
    assert.equal(parseItemIntent(value, { now: NOW, timeZone: TZ }), null);
  }
});

// ── 回话 ────────────────────────────────────────────────────

test("列表里带序号，并且告诉他怎么划掉——否则他不知道下一步", () => {
  const message = buildListMessage("todo", [
    { title: "买菜", dueAt: null },
    { title: "交房租", dueAt: "2026-07-31T02:00:00.000Z" },
  ], { formatTime: () => "7-31 10:00" });

  assert.match(message, /1\. 买菜/);
  assert.match(message, /2\. 交房租（7-31 10:00）/);
  assert.match(message, /完成 序号/);
});

test("列表最多 10 条——一次甩 30 条给一个 ADHD 的人等于什么都没给", () => {
  const many = Array.from({ length: 24 }, (_, index) => ({
    title: `第${index + 1}件`, dueAt: null,
  }));

  const message = buildListMessage("todo", many);

  assert.match(message, /10\. 第10件/);
  assert.ok(!message.includes("11. "), "超过 10 条还在往下列");
  assert.match(message, /还有 14 条/);
});

test("空的时候说人话，不是「暂无数据」", () => {
  assert.equal(buildListMessage("todo", []), "待办是空的，挺好。");
  assert.equal(buildListMessage("event", []), "日程是空的。");
});

test("加完和划掉都回一句短的", () => {
  assert.equal(buildAddedMessage({ kind: "todo", title: "买菜" }), "记下了：买菜");
  assert.equal(
    buildAddedMessage({ kind: "event", title: "开会", dueAtLabel: "明天 15:00" }),
    "记下了：开会（明天 15:00）",
  );
  assert.equal(buildDoneMessage({ title: "买菜" }), "划掉了：买菜");
});

test("说不清划哪条的时候，问清楚而不是乱划一条", () => {
  assert.equal(buildDoneFailedMessage(0), "待办本来就是空的。");
  assert.match(buildDoneFailedMessage(3), /现在有 3 条/);
});
